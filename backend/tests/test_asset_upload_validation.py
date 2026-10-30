from io import BytesIO
import subprocess
import wave

import pytest
from PIL import Image

from app.services.asset_upload import validate_and_upload_asset


def test_asset_image_normalized_before_upload():
    source = BytesIO()
    Image.new("RGB", (32, 64)).save(source, "JPEG")
    source.write(b"trailing-private-data")
    def upload(stream, extension, content_type):
        raw = stream.read()
        assert extension == ".png"
        assert content_type == "image/png"
        assert b"trailing-private-data" not in raw
        with Image.open(BytesIO(raw)) as image:
            assert image.size == (32, 64)
        return "canonical-url"
    assert validate_and_upload_asset(source, upload) == ("canonical-url", False)


def test_asset_real_wav_is_probed_without_external_service():
    source = BytesIO()
    with wave.open(source, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 800)
    def upload(stream, extension, content_type):
        assert extension == ".wav"
        assert content_type == "audio/wav"
        assert stream.read(4) == b"RIFF"
        return "audio-url"
    assert validate_and_upload_asset(source, upload) == ("audio-url", True)


@pytest.mark.parametrize("raw", [b"<script>alert(1)</script>", b"\x89PNG\r\n\x1a\nspoof", b"ID3not-really-audio"])
def test_asset_invalid_content_never_uploaded(raw):
    called = []
    with pytest.raises(ValueError):
        validate_and_upload_asset(BytesIO(raw), lambda *args: called.append(args))
    assert not called


def test_asset_probe_timeout_is_bounded(monkeypatch):
    def timeout(args, **kwargs):
        assert 0 < kwargs["timeout"] <= 15
        assert kwargs["capture_output"]
        assert "file,pipe" in args
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ValueError, match="超时"):
        validate_and_upload_asset(BytesIO(b"ID3placeholder"), lambda *args: None)


def test_asset_rejects_video_even_with_audio(monkeypatch):
    from app.services import asset_upload
    def result(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=b'{"streams":[{"codec_type":"audio","codec_name":"aac"},{"codec_type":"video"}],"format":{"format_name":"mov,mp4,m4a","duration":"1"}}')
    monkeypatch.setattr(subprocess, "run", result)
    with pytest.raises(ValueError, match="不支持视频"):
        asset_upload.validate_and_upload_asset(BytesIO(b"\0\0\0\x18ftypM4A "), lambda *args: None)
