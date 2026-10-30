"""Bounded avatar decoding: only normalized pixel data reaches public storage."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO
from uuid import uuid4
import warnings

from PIL import Image, UnidentifiedImageError


def normalize_avatar(source: BinaryIO, directory: Path, *, prefix: str = "avatar", max_dimension: int | None = 1024) -> Path:
    """Verify real format, cap pixels and strip metadata, animation and trailing data."""
    normalized = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                    raise ValueError("仅支持 JPG / PNG / WebP / GIF")
                if image.width * image.height > 16_000_000 or max(image.size) > 8192:
                    raise ValueError("头像尺寸过大")
                image.verify()
            source.seek(0)
            with Image.open(source) as image:
                image.load()
                normalized = image.convert("RGBA")
                if max_dimension is not None:
                    normalized.thumbnail((max_dimension, max_dimension))
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("头像不是有效图片") from exc
    directory.mkdir(parents=True, exist_ok=True)
    # Unique names also avoid a concurrent upload replacing another request's file.
    destination = directory / f"{prefix}-{uuid4().hex}.png"
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            normalized.save(stream, format="PNG")
        temporary.replace(destination)
    finally:
        if normalized is not None:
            normalized.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


async def receive_image_upload(file, directory: Path, *, max_bytes: int, prefix: str,
                               max_dimension: int | None = None) -> Path:
    """Bounded streaming transport shared by image routes; disk and decoding off loop."""
    import asyncio
    from tempfile import SpooledTemporaryFile
    from fastapi import HTTPException

    with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as source:
        total = 0
        try:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(400, f"图片不能超过 {max_bytes // (1024 * 1024)}MB")
                await asyncio.to_thread(source.write, chunk)
            if not total:
                raise HTTPException(400, "空文件")
            source.seek(0)
            return await asyncio.to_thread(normalize_avatar, source, directory,
                                           prefix=prefix, max_dimension=max_dimension)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            await file.close()
