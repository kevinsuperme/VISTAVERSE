from datetime import datetime

import json

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="默认 Key", max_length=64)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(ApiKeyOut):
    secret: str


class V1ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative: str = Field(default="", max_length=2000)
    ratio: str = Field(default="1:1", description="1:1 | 16:9 | 9:16")
    image_url: str | None = Field(
        default=None,
        max_length=2048,
        description="参考图 HTTPS URL，传入则为图生图",
    )


class V1VideoGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    image_url: str = Field(min_length=8, max_length=2048, description="首帧图 HTTPS URL")
    duration: int = Field(default=5, ge=4, le=15)
    resolution: str = Field(default="480p")
    generate_audio: bool = False


class V1SeedanceTaskRequest(BaseModel):
    """接近火山 Seedance 的任务体，服务端补全 model 并转发。"""

    content: list[dict] = Field(min_length=1, max_length=20)
    duration: int | None = Field(default=None, ge=4, le=30)
    resolution: str = Field(default="480p")
    ratio: str | None = None
    generate_audio: bool = False
    return_last_frame: bool = True
    watermark: bool = False

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: list[dict]) -> list[dict]:
        total_bytes = 0
        media_types = {"image_url", "audio_url", "video_url"}
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("content 项必须是对象")
            total_bytes += len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
            kind = str(item.get("type") or "").strip()
            if kind == "text":
                text = item.get("text")
                if not isinstance(text, str) or len(text) > 8000:
                    raise ValueError("文本内容不能为空且不能超过 8000 字符")
            elif kind in media_types:
                raw = item.get(kind)
                url = raw.get("url") if isinstance(raw, dict) else raw
                if not isinstance(url, str) or not url.strip() or len(url.strip()) > 2048:
                    raise ValueError("媒体 URL 必须是 2048 字符以内的非空字符串")
                # The upstream adapter expects the OpenAI-style `{url: ...}`
                # object. Normalize the compact string form at the boundary.
                if isinstance(raw, str):
                    item[kind] = {"url": raw.strip()}
            else:
                raise ValueError("content 类型仅支持 text、image_url、audio_url、video_url")
        if total_bytes > 64 * 1024:
            raise ValueError("content 总大小不能超过 64KB")
        return value


class V1GenerationOut(BaseModel):
    status: str
    kind: str
    urls: list[str] = Field(default_factory=list)
    task_id: str | None = None
    preview_url: str | None = None
    error: str | None = None
