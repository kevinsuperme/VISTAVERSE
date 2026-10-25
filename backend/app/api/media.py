"""签名媒体下载接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.media_access import (
    local_media_path,
    signed_media_url,
    user_owns_media,
    verify_media_signature,
)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/sign", include_in_schema=False)
async def sign_media(
    url: str = Query(..., min_length=1, max_length=2048),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    if not await user_owns_media(db, user.id, url):
        raise HTTPException(status_code=404, detail="媒体不存在")
    signed = signed_media_url(url)
    if not signed:
        raise HTTPException(status_code=400, detail="仅支持本地生成媒体")
    return {"url": signed}


@router.get("/{path:path}", include_in_schema=False)
async def get_media(
    path: str,
    expires: int = Query(..., ge=1),
    signature: str = Query(..., min_length=16, max_length=128),
) -> FileResponse:
    if not verify_media_signature(path, expires, signature):
        raise HTTPException(status_code=403, detail="媒体链接无效或已过期")
    local = local_media_path(path)
    if not local or not local.is_file():
        raise HTTPException(status_code=404, detail="媒体不存在")
    return FileResponse(local, headers={"Cache-Control": "private, max-age=60"})

