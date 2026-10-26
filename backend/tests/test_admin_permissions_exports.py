"""后台角色边界、默认拒绝、CSV 和批量入参回归，不依赖数据库。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.admin import router
from app.api.admin.users import patch_user
from app.database import get_db
from app.deps import get_current_user
from app.schemas import AdminUserPatch, AdminWorkPatch, UserOut
from app.schemas_admin import AdminTemplateBulk, AdminWorkBulk
from app.services.admin.exports import EXPORT_LIMIT, csv_response
from app.services.admin.permissions import permissions_for, route_permissions
from app.services.admin.work_review import validate_review


def test_all_admin_routes_require_registered_permission():
    """新增管理路由未登记权限时直接阻断回归。"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    for route in app.routes:
        if route.path.startswith("/api/admin"):
            for method in route.methods:
                assert route_permissions(method, route.path), (method, route.path)
    assert not route_permissions("DELETE", "/api/admin/users/{user_id}")
    assert not route_permissions("GET", "/api/admin/new-unregistered-route")


@pytest.mark.parametrize(("role", "method", "path", "body"), [
    ("user", "GET", "/api/admin/users", None),
    ("admin_readonly", "POST", "/api/admin/works/bulk", {"ids": [1], "audit_status": "passed"}),
    ("admin_operator", "PATCH", "/api/admin/users/1", {"balance_delta_fen": 1}),
    ("admin_finance", "PATCH", "/api/admin/users/1", {"balance_delta_fen": 1, "role": "admin"}),
    ("admin_finance", "PATCH", "/api/admin/users/1", {"plan": "pro"}),
    ("admin_reviewer", "GET", "/api/admin/stats", None),
    ("admin_reviewer", "GET", "/api/admin/finance/export", None),
    ("admin_operator", "GET", "/api/admin/settings/models", None),
])
def test_forbidden_http_requests_do_not_reach_database(role, method, path, body):
    """真实路由鉴权和字段级校验必须早于数据库变更。"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=100, role=role)
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 403, response.text


def test_me_permissions_follow_role_and_unknown_role_is_denied():
    """返回权限不能因客户端传入缓存字段而扩大。"""
    user = UserOut(id=1, email="admin@example.com", nickname="a", quota_left=0, role="admin_reviewer")
    assert user.model_dump()["permissions"] == permissions_for("admin_reviewer")
    assert "works:review" in user.permissions
    assert "dashboard:read" not in user.permissions
    assert permissions_for("admin_undefined") == []


@pytest.mark.asyncio
async def test_compound_patch_checks_every_permission_before_change():
    """财务可以调账，但混入提权字段时整单拒绝。"""
    with pytest.raises(HTTPException) as caught:
        await patch_user(1, AdminUserPatch(role="admin", balance_delta_fen=100),
                         SimpleNamespace(id=9, role="admin_finance"), None)
    assert caught.value.status_code == 403


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_reject_requires_audit_reason_even_with_whitespace(reason):
    """状态前后空白不能绕过驳回理由校验。"""
    with pytest.raises(HTTPException):
        validate_review(AdminWorkPatch(audit_status=" rejected ", audit_reason=reason))


def test_bulk_boundaries_and_duplicates():
    """重复、非正 ID 和超限批量请求不进入事务。"""
    for ids in ([1, 1], [0], list(range(1, 52))):
        with pytest.raises(ValidationError):
            AdminWorkBulk(ids=ids, audit_status="passed")
    with pytest.raises(ValidationError):
        AdminTemplateBulk(ids=["a", "a"], is_active=False)


@pytest.mark.parametrize("body", [{"balance_note": "长" * 256}, {"balance_delta_fen": 2_147_483_648}, {"balance_fen": -1}])
def test_balance_inputs_fail_validation_before_database(body):
    """调账输入匹配 PostgreSQL 列范围，返回校验错误而不是提交时 500。"""
    with pytest.raises(ValidationError):
        AdminUserPatch(**body)


def test_csv_blocks_formula_injection_and_rejects_truncation():
    """保留负数值，转义攻击文本；超限不能返回看似完整的文件。"""
    response = csv_response("safe.csv", ["名称", "金额"], [[" \t=HYPERLINK(1)", -100], ["@SUM(1)", 2]])
    data = response.body.decode("utf-8-sig")
    assert "' \t=HYPERLINK(1)" in data
    assert "'@SUM(1)" in data
    assert ",-100" in data
    with pytest.raises(HTTPException) as caught:
        csv_response("large.csv", ["id"], ((i,) for i in range(EXPORT_LIMIT + 1)))
    assert caught.value.status_code == 400
