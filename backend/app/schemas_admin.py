"""管理端批量操作与通知参数，限制单次请求规模。"""

from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas import AdminWorkPatch


class AdminWorkBulk(AdminWorkPatch):
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=50)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, ids: list[int]) -> list[int]:
        """拒绝重复 ID，避免结果数量和审计记录歧义。"""
        if len(ids) != len(set(ids)):
            raise ValueError("不能重复选择同一作品")
        return ids


class AdminTemplateBulk(BaseModel):
    ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(min_length=1, max_length=50)
    is_active: bool

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, ids: list[str]) -> list[str]:
        """确保每个模板只被操作一次。"""
        if len(ids) != len(set(ids)):
            raise ValueError("不能重复选择同一模板")
        return ids


class AdminNotificationReadPatch(BaseModel):
    ids: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=1, max_length=100)
