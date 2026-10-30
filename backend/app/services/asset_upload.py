"""Validate asset media using bounded copies, decoded pixels and local ffprobe."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Callable, TypeVar

from app.config import get_settings
from app.services.avatar_upload import normalize_avatar

T = TypeVar("T")


def _probe_audio(path: Path) -> tuple[str, str]:
    settings = get_settings()
    timeout = max(1.0, min(float(settings.ffmpeg_timeout_sec), 15.0))
    try:
        result = subprocess.run(
            [settings.ffprobe_path, "-v", "error", "-protocol_whitelist", "file,pipe",
             "-probesize", "1048576", "-analyzeduration", "3000000",
             "-show_entries", "stream=codec_type,codec_name:format=format_name,duration",
             "-of", "json", str(path)],
            capture_output=True, timeout=timeout, check=True,
        )
        data = json.loads(result.stdout)
    except FileNotFoundError as exc:
        raise RuntimeError("音频校验服务不可用") from exc
    except (subprocess.SubprocessError, ValueError) as exc:
        raise ValueError("文件不是有效音频或校验超时") from exc
    streams = data.get("streams") or []
    if len(streams) != 1 or streams[0].get("codec_type") != "audio":
        raise ValueError("仅支持单音轨文件，不支持视频或附加流")
    codec = streams[0].get("codec_name")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0 or duration > 3600:
        raise ValueError("音频时长须在 0 到 3600 秒内")
    formats = set(str((data.get("format") or {}).get("format_name") or "").split(","))
    if "mp3" in formats and codec == "mp3":
        return ".mp3", "audio/mpeg"
    if "wav" in formats and str(codec).startswith("pcm_"):
        return ".wav", "audio/wav"
    if "m4a" in formats and codec in {"aac", "alac"}:
        return ".m4a", "audio/mp4"
    if "aac" in formats and codec == "aac":
        return ".aac", "audio/aac"
    if "ogg" in formats and codec in {"vorbis", "opus", "flac"}:
        return ".ogg", "audio/ogg"
    if "webm" in formats and codec in {"vorbis", "opus"}:
        return ".webm", "audio/webm"
    raise ValueError("不支持的音频容器或编码")


def validate_and_upload_asset(source: BinaryIO, upload: Callable[[BinaryIO, str, str], T]) -> tuple[T, bool]:
    """Never trust MIME/name. Originals remain temporary; upload only after validation.

    Images: 20 MiB input, decoded 16M pixels and 8192 max edge, normalized PNG.
    Audio: 30 MiB input, exactly one real audio stream, <= 1 hour, bounded probe.
    The caller executes this entire synchronous function in its worker pool.
    """
    from app.services.studio_tools import _magic_matches

    source.seek(0)
    header = source.read(32)
    source.seek(0)
    image = any(_magic_matches(ext, header) for ext in (".png", ".jpg", ".gif", ".webp"))
    if not image and not (
        header.startswith((b"ID3", b"OggS", b"\x1aE\xdf\xa3"))
        or (len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE")
        or (len(header) >= 12 and header[4:8] == b"ftyp")
        or (len(header) >= 2 and header[0] == 0xff and header[1] & 0xe0 == 0xe0)
    ):
        raise ValueError("仅支持有效图片或 MP3/WAV/M4A/AAC/OGG/WebM 音频")
    limit = (20 if image else 30) * 1024 * 1024
    with TemporaryDirectory(prefix="vistaverse-asset-") as temporary:
        root = Path(temporary)
        path = root / "source.upload"
        total = 0
        with path.open("wb") as target:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError("图片不能超过 20MB" if image else "音频不能超过 30MB")
                target.write(chunk)
        if image:
            with path.open("rb") as original:
                normalized = normalize_avatar(original, root, prefix="asset", max_dimension=None)
            extension, content_type = ".png", "image/png"
            path = normalized
        else:
            extension, content_type = _probe_audio(path)
        with path.open("rb") as validated:
            return upload(validated, extension, content_type), not image
