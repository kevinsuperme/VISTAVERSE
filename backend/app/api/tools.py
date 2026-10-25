"""独立创作工具 API：/api/tools/*"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import ToolRun, User
from app.schemas_tools import ToolRunListOut, ToolRunOut, ToolRunRecordOut, ToolTaskOut
from app.services.billing import (
    run_billed_ephemeral_deferred,
    settle_deferred_video_poll,
)
from app.services.studio_tools import (
    UploadTooLargeError,
    enqueue_image_tool,
    get_tool_run,
    list_tool_runs,
    persist_tool_run,
    poll_image_tool_task,
    poll_video_task,
    save_upload_stream,
    start_video_tool,
    update_tool_run_task,
)

router = APIRouter(prefix="/tools", tags=["tools"])
logger = logging.getLogger("app.api.tools")

IMAGE_TOOLS = {"t2i", "i2i", "i2p", "ecom"}
VIDEO_TOOLS = {"t2v", "v2v"}


def _cleanup_saved(paths: list[Path]) -> None:
    """清理上传失败后的临时媒体，不让清理异常覆盖原始错误。"""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("failed to remove temporary upload path=%s", path)


# 提交独立工具生成（生图走统一任务平台；生视频返回 Seedance task_id 供轮询）
@router.post("/run", response_model=ToolRunOut)
async def run_tool(
    tool_id: str = Form(...),
    prompt: str = Form(""),
    negative: str = Form(""),
    ratio: str = Form(""),
    strength: str = Form(""),
    mode: str = Form(""),
    pack: str = Form(""),
    duration: str = Form(""),
    motion: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolRunOut:
    tid = (tool_id or "").strip()
    if tid not in IMAGE_TOOLS | VIDEO_TOOLS:
        # 在处理上传内容前校验工具，避免未知 tool_id 也能消耗磁盘、CPU
        # 和请求体带宽。
        raise HTTPException(status_code=400, detail="未知工具")
    settings = get_settings()
    upload_files = list(files or [])
    if len(upload_files) > settings.upload_max_files:
        raise HTTPException(
            status_code=413,
            detail=f"最多上传 {settings.upload_max_files} 个文件",
        )
    saved: list[Path] = []
    total_upload_bytes = 0
    tool_params = {
        "negative": negative,
        "ratio": ratio,
        "strength": strength,
        "mode": mode,
        "pack": pack,
        "duration": duration,
        "motion": motion,
    }
    try:
        for item in upload_files:
            remaining = settings.upload_max_total_bytes - total_upload_bytes
            if remaining <= 0:
                raise UploadTooLargeError(
                    f"上传文件总大小不能超过 {settings.upload_max_total_bytes // (1024 * 1024)}MB"
                )
            try:
                path, size = await run_in_threadpool(
                    save_upload_stream,
                    user.id,
                    item.file,
                    item.filename or "upload.bin",
                    max_bytes=min(settings.upload_max_file_bytes, remaining),
                )
            finally:
                await item.close()
            total_upload_bytes += size
            saved.append(path)
        if tid in IMAGE_TOOLS:
            try:
                data = await enqueue_image_tool(
                    db,
                    user,
                    tool_id=tid,
                    prompt=prompt,
                    negative=negative,
                    ratio=ratio or None,
                    strength=strength or None,
                    mode=mode or None,
                    pack=pack or None,
                    files=saved,
                    params=tool_params,
                )
            except ValueError as exc:
                raise HTTPException(status_code=402, detail=str(exc)) from exc
        elif tid in VIDEO_TOOLS:
            async def _exec_video() -> dict:
                return await start_video_tool(
                    db,
                    user,
                    tool_id=tid,
                    prompt=prompt,
                    ratio=ratio or None,
                    duration_raw=duration or None,
                    motion=motion or None,
                    files=saved,
                )

            try:
                billing_task, data = await run_billed_ephemeral_deferred(
                    db,
                    user,
                    domain="studio",
                    task_type="tool_video",
                    executor=_exec_video,
                    payload=tool_params,
                    commit=False,
                )
            except ValueError as exc:
                raise HTTPException(status_code=402, detail=str(exc)) from exc
            data = {**data, "billing_task_id": billing_task.id}
            await persist_tool_run(
                db,
                user_id=user.id,
                tool_id=tid,
                prompt=prompt,
                params={**tool_params, "billing_task_id": billing_task.id},
                data=data,
            )
        else:
            raise ValueError("未知工具")
        await db.commit()
    except HTTPException:
        _cleanup_saved(saved)
        raise
    except UploadTooLargeError as exc:
        _cleanup_saved(saved)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        _cleanup_saved(saved)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _cleanup_saved(saved)
        logger.exception("tool run failed user=%s tool=%s", user.id, tid)
        raise HTTPException(status_code=500, detail="工具处理失败，请稍后重试") from exc
    return ToolRunOut.model_validate(data)


# 查询工具异步任务（生图任务平台 / 生视频 Seedance），并回写创作记录
@router.get("/tasks/{task_id}", response_model=ToolTaskOut)
async def get_tool_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolTaskOut:
    if not task_id.strip():
        raise HTTPException(status_code=400, detail="缺少任务")
    tid = task_id.strip()
    row = (
        await db.execute(
            select(ToolRun).where(ToolRun.user_id == user.id, ToolRun.task_id == tid).limit(1)
        )
    ).scalar_one_or_none()
    billing_task_id: int | None = None
    # 本地无归属记录即拒绝：上游 task_id 可被持有者之外的人猜测传递，
    # 不能在没有归属凭据时代理查上游（视频 URL 会被拖走）。
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if isinstance(row.params, dict):
        raw_bid = row.params.get("billing_task_id")
        if raw_bid is not None:
            try:
                billing_task_id = int(raw_bid)
            except (TypeError, ValueError):
                billing_task_id = None
    if row.kind == "image":
        data = await poll_image_tool_task(db, user, tid)
    else:
        data = await poll_video_task(user, tid)
        await settle_deferred_video_poll(
            db,
            user,
            provider_task_id=tid,
            poll_status=str(data.get("status") or ""),
            error=str(data.get("error") or "") or None,
            billing_task_id=billing_task_id,
            usage_tokens=int((data.get("usage") or {}).get("total_tokens") or 0),
            completion_tokens=int((data.get("usage") or {}).get("completion_tokens") or 0),
            raw_usage=data.get("raw_usage") if isinstance(data.get("raw_usage"), dict) else None,
        )
    await update_tool_run_task(db, user.id, tid, data)
    await db.commit()
    return ToolTaskOut.model_validate(data)


# 把 ORM 记录转成列表/详情项（时间用 ISO）
def _record_out(row: ToolRun) -> ToolRunRecordOut:
    created = row.created_at.isoformat() if row.created_at else ""
    return ToolRunRecordOut(
        id=row.id,
        tool_id=row.tool_id,
        kind=row.kind,
        status=row.status,
        prompt=row.prompt or "",
        preview_url=row.preview_url,
        urls=list(row.urls or []),
        task_id=row.task_id,
        params=row.params if isinstance(row.params, dict) else None,
        error=row.error,
        created_at=created,
    )


# 个人中心：当前用户的工具创作记录（服务端分页）
@router.get("/runs", response_model=ToolRunListOut)
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolRunListOut:
    rows, total = await list_tool_runs(db, user.id, page=page, page_size=page_size)
    await db.commit()
    return ToolRunListOut(
        items=[_record_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# 个人中心：单条创作详情（含 OSS 结果地址）
@router.get("/runs/{run_id}", response_model=ToolRunRecordOut)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolRunRecordOut:
    row = await get_tool_run(db, user.id, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    await db.commit()
    return _record_out(row)
