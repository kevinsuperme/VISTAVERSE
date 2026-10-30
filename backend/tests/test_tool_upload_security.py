"""工具上传的类型、大小和临时文件清理回归测试。"""

from __future__ import annotations

from io import BytesIO
import shutil
import subprocess

import pytest
from app.services import studio_tools


def _patch_tools_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(studio_tools, "tools_dir", lambda _user_id: tmp_path / "tools")


def test_save_upload_stream_checks_magic_and_replaces_atomically(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _patch_tools_dir(monkeypatch, tmp_path)
    from PIL import Image
    stream = BytesIO()
    Image.new("RGB", (16, 32)).save(stream, "PNG")
    raw = stream.getvalue() + b"trailing payload"

    path, size = studio_tools.save_upload_stream(
        7, BytesIO(raw), "reference.png", max_bytes=1024
    )

    assert path.is_file()
    assert b"trailing payload" not in path.read_bytes()
    with Image.open(path) as image:
        assert image.size == (16, 32)
    assert size == len(raw)
    assert not list((tmp_path / "tools").glob("*.part"))


def test_save_upload_stream_rejects_extension_spoof_and_cleans_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _patch_tools_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="内容与扩展名不匹配"):
        studio_tools.save_upload_stream(
            7, BytesIO(b"not-an-image"), "reference.png", max_bytes=1024
        )

    tool_dir = tmp_path / "tools"
    assert not list(tool_dir.glob("*"))


def test_save_upload_stream_rejects_oversize_before_persisting(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _patch_tools_dir(monkeypatch, tmp_path)
    raw = b"\x89PNG\r\n\x1a\n" + b"x" * 20

    with pytest.raises(ValueError, match="不能超过"):
        studio_tools.save_upload_stream(7, BytesIO(raw), "reference.png", max_bytes=8)

    assert not list((tmp_path / "tools").glob("*"))



def test_tool_upload_rejects_fake_magic_and_cleans_partial(monkeypatch, tmp_path):
    _patch_tools_dir(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="有效图片"):
        studio_tools.save_upload_stream(7, BytesIO(b"\x89PNG\r\n\x1a\nspoof"), "reference.png", max_bytes=1024)
    assert not list((tmp_path / "tools").glob("*"))


def test_tool_video_upload_accepts_real_mp4_and_rejects_fake(monkeypatch, tmp_path):
    _patch_tools_dir(monkeypatch, tmp_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    generated = tmp_path / "sample.mp4"
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.2",
         "-an", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(generated)],
        capture_output=True, check=True, timeout=15,
    )
    raw = generated.read_bytes()
    path, size = studio_tools.save_upload_stream(7, BytesIO(raw), "clip.mp4", max_bytes=1024 * 1024)
    assert path.is_file() and size == len(raw)
    with pytest.raises(ValueError, match="有效视频"):
        studio_tools.save_upload_stream(7, BytesIO(b"\0\0\0\x18ftypisomfake"), "bad.mp4", max_bytes=1024)


def test_tool_video_probe_rejects_extra_stream_and_bounds_timeout(monkeypatch, tmp_path):
    _patch_tools_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(studio_tools.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(
        subprocess.TimeoutExpired(args[0], kwargs["timeout"])))
    with pytest.raises(ValueError, match="超时"):
        studio_tools.save_upload_stream(7, BytesIO(b"\0\0\0\x18ftypisomfake"), "bad.mp4", max_bytes=1024)


@pytest.mark.parametrize("streams", [
    [{"codec_type":"audio"}],
    [{"codec_type":"video","width":16,"height":16},{"codec_type":"attachment"}],
    [{"codec_type":"video","width":16384,"height":16}],
])
def test_tool_video_rejects_invalid_streams(monkeypatch, tmp_path, streams):
    import json
    _patch_tools_dir(monkeypatch, tmp_path)
    def probe(*args, **kwargs):
        assert 0 < kwargs["timeout"] <= 15
        assert "file,pipe" in args[0]
        return subprocess.CompletedProcess(args[0], 0, json.dumps({"streams": streams, "format": {"format_name":"mov,mp4", "duration":"1"}}).encode())
    monkeypatch.setattr(studio_tools.subprocess, "run", probe)
    with pytest.raises(ValueError):
        studio_tools.save_upload_stream(7, BytesIO(b"\0\0\0\x18ftypisomfake"), "bad.mp4", max_bytes=1024)
    assert not list((tmp_path / "tools").glob("*"))
