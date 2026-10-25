"""独立创作工具请求 / 响应。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_serializer


def _protect_media(value: str | None) -> str | None:
    if not value:
        return value
    from app.services.storage import protect_media_url

    return protect_media_url(value)


class ToolRunOut(BaseModel):
    kind: str = Field(description="image | video | images")
    urls: list[str] = Field(default_factory=list)
    task_id: str | None = None
    status: str = "succeeded"
    preview_url: str | None = None
    message: str | None = None

    @field_serializer("urls")
    def serialize_media_urls(self, value: list[str]) -> list[str]:
        return [_protect_media(item) or "" for item in value]

    @field_serializer("preview_url")
    def serialize_media_url(self, value: str | None) -> str | None:
        return _protect_media(value)


class ToolTaskOut(BaseModel):
    status: str
    kind: str = "video"
    urls: list[str] = Field(default_factory=list)
    error: str | None = None

    @field_serializer("urls")
    def serialize_media_urls(self, value: list[str]) -> list[str]:
        return [_protect_media(item) or "" for item in value]


class ToolRunRecordOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tool_id: str
    kind: str
    status: str
    prompt: str = ""
    preview_url: str | None = None
    urls: list[str] = Field(default_factory=list)
    task_id: str | None = None
    params: dict | None = None
    error: str | None = None
    created_at: str

    @field_serializer("urls")
    def serialize_media_urls(self, value: list[str]) -> list[str]:
        return [_protect_media(item) or "" for item in value]

    @field_serializer("preview_url")
    def serialize_media_url(self, value: str | None) -> str | None:
        return _protect_media(value)


class ToolRunListOut(BaseModel):
    items: list[ToolRunRecordOut]
    total: int
    page: int
    page_size: int
