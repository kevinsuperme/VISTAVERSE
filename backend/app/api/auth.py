from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
import asyncio
from tempfile import SpooledTemporaryFile
from app.services.avatar_upload import normalize_avatar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User, WalletLedger
from app.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services import storage
from app.services.auth import (
    create_access_token,
    get_user_by_email,
    hash_password,
    verify_password,
)
from app.services.password_reset import (
    InvalidTokenError,
    RedisUnavailableError,
    apply_password_reset,
    request_password_reset,
)
from app.services.profile import ProfileError, prepare_profile_update

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    email_norm = str(body.email).strip().lower()
    existing = await get_user_by_email(db, email_norm)
    if existing:
        raise HTTPException(status_code=400, detail="邮箱已注册")
    grant = int(settings.billing_signup_grant_fen or 0)
    user = User(
        email=email_norm,
        nickname=body.nickname,
        hashed_password=hash_password(body.password),
        quota_left=settings.new_user_quota,
        balance_fen=grant,
        plan="free",
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        # The pre-check is advisory under concurrent registration; normalize
        # the unique-key race into the same user-facing response.
        await db.rollback()
        raise HTTPException(status_code=400, detail="邮箱已注册") from exc
    if grant > 0:
        db.add(
            WalletLedger(
                user_id=user.id,
                delta_fen=grant,
                balance_after=grant,
                kind="grant",
                ref_type="signup",
                ref_id=str(user.id),
                note="signup_grant",
            )
        )
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await get_user_by_email(db, body.email.lower())
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """校验当前密码后写入新密码。"""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """发送密码重置邮件；统一成功文案，避免邮箱枚举。"""
    try:
        return await request_password_reset(db, str(body.email))
    except RedisUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """用邮件中的一次性 token 设置新密码。"""
    try:
        await apply_password_reset(db, token=body.token, new_password=body.new_password)
    except RedisUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """更新当前用户的用户名、登录邮箱与联系手机号（仅记录，无验证码）。"""
    try:
        fields = prepare_profile_update(
            nickname=body.nickname,
            email=body.email,
            phone=body.phone,
        )
    except ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if fields["email"] != user.email:
        taken = await get_user_by_email(db, fields["email"])
        if taken and taken.id != user.id:
            raise HTTPException(status_code=400, detail="该邮箱已被使用")

    user.nickname = fields["nickname"]
    user.email = fields["email"]
    user.phone = fields["phone"]
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="该邮箱已被使用") from exc
    await db.refresh(user)
    return user


@router.post("/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Upload or replace the current user's profile avatar."""
    max_bytes = 5 * 1024 * 1024
    # Spool to disk after 1 MiB; the original upload is never served.
    with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as source:
        total = 0
        try:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=400, detail="头像不能超过 5MB")
                await asyncio.to_thread(source.write, chunk)
            if not total:
                raise HTTPException(status_code=400, detail="空文件")
            source.seek(0)
            dest = await asyncio.to_thread(normalize_avatar, source, storage.user_dir(user.id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await file.close()
    user.avatar_url = await asyncio.to_thread(storage.publish_local, dest)
    await db.commit()
    await db.refresh(user)
    return user
