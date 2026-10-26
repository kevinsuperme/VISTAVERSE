"""共享列表筛选和 CSV 安全导出边界。"""

import csv
import io
from collections.abc import Iterable

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import cast, or_
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Template, Work

EXPORT_LIMIT = 10_000


def work_filters(audit_status=None, visibility=None, q=None, user_id=None) -> list:
    """列表和导出复用同一组 SQL 条件。"""
    conditions = []
    for value, column in ((audit_status, Work.audit_status), (visibility, Work.visibility)):
        if value and value.strip():
            conditions.append(column == value.strip())
    if q and q.strip():
        conditions.append(Work.title.ilike(f"%{q.strip()}%"))
    if user_id is not None:
        conditions.append(Work.user_id == user_id)
    return conditions


def template_filters(q=None, is_active=None, category=None, is_premium=None) -> list:
    """模板 Premium 和分类筛选始终由数据库执行。"""
    conditions = []
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append(or_(Template.id.ilike(like), Template.name.ilike(like), Template.description.ilike(like)))
    if is_active is not None:
        conditions.append(Template.is_active == is_active)
    if is_premium is not None:
        conditions.append(Template.is_premium == is_premium)
    if category and category.strip():
        conditions.append(cast(Template.category, JSONB).contains([category.strip()]))
    return conditions


def csv_cell(value):
    """阻断公式和前导空白绕过；真实数值仍按数值输出。"""
    if value is None:
        return ""
    if isinstance(value, str) and value.lstrip(" \t\r\n\v\f\ufeff\u200b").lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def csv_response(filename: str, headers: list[str], rows: Iterable) -> Response:
    """有界导出，超限明确拒绝，不静默丢行；BOM 兼容中文 Excel。"""
    buffer = io.StringIO(newline="")
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for index, row in enumerate(rows):
        if index >= EXPORT_LIMIT:
            raise HTTPException(status_code=400, detail="导出最多 10000 条，请缩小筛选范围")
        writer.writerow([csv_cell(value) for value in row])
    return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
