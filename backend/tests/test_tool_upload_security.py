"""工具上传的类型、大小和临时文件清理回归测试。"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.services import studio_tools


def _patch_tools_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(studio_tools, "tools_dir", lambda _user_id: tmp_path / "tools")


def test_save_upload_stream_checks_magic_and_replaces_atomically(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _patch_tools_dir(monkeypatch, tmp_path)
    raw = b"\x89PNG\r\n\x1a\n" + b"payload"

    path, size = studio_tools.save_upload_stream(
        7, BytesIO(raw), "reference.png", max_bytes=1024
    )

    assert path.is_file()
    assert path.read_bytes() == raw
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

