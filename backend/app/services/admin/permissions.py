"""后台角色与路由权限的单一真相源；新增路由必须显式登记。"""

from fastapi import HTTPException

READ_PERMISSIONS = frozenset({
    "dashboard:read", "users:read", "orders:read", "finance:read", "tasks:read",
    "content:read", "works:read", "templates:read", "notifications:read",
})
ROLE_PERMISSIONS = {
    "admin": READ_PERMISSIONS | {
        "users:write", "users:role", "balance:write", "finance:write", "tasks:write",
        "content:write", "works:review", "templates:write", "settings:read", "settings:write",
    },
    "admin_readonly": READ_PERMISSIONS,
    "admin_operator": READ_PERMISSIONS | {"users:write", "content:write", "tasks:write", "templates:write"},
    "admin_finance": frozenset({"dashboard:read", "users:read", "orders:read", "finance:read", "finance:write", "balance:write", "notifications:read"}),
    "admin_reviewer": frozenset({"content:read", "works:read", "works:review", "templates:read", "notifications:read"}),
}


def permissions_for(role: str | None) -> list[str]:
    """返回稳定排序的公开权限列表；普通用户和未知角色无后台权限。"""
    return sorted(ROLE_PERMISSIONS.get(role or "user", ()))


def require_permission(user, permission: str) -> None:
    """对字段级操作再次鉴权，避免复合 PATCH 越权。"""
    if permission not in permissions_for(getattr(user, "role", None)):
        raise HTTPException(status_code=403, detail="没有执行此操作的权限")


def route_permissions(method: str, path: str) -> frozenset[str]:
    """将 FastAPI 路由模板映射到允许的权限，未知路由默认拒绝。"""
    routes = {
        "GET": {
            "/stats": "dashboard:read", "/stats/upstream-usage": "finance:read",
            "/users": "users:read", "/users/{user_id}": "users:read",
            "/orders": "orders:read", "/orders/{order_id}": "orders:read",
            "/ledger": "finance:read", "/usage-events": "finance:read",
            "/finance/daily": "finance:read", "/finance/export": "finance:read",
            "/queues": "tasks:read", "/tasks": "tasks:read", "/tasks/stats": "tasks:read",
            "/tasks/{task_id}": "tasks:read", "/tasks/{task_id}/events": "tasks:read",
            "/works": "works:read", "/works/{work_id}": "works:read", "/works/export": "works:read",
            "/templates": "templates:read", "/templates/meta": "templates:read",
            "/templates/{template_id}": "templates:read", "/templates/export": "templates:read",
            "/notifications": "notifications:read",
            "/settings/routing": "settings:read", "/settings/models": "settings:read",
            "/settings/billing/model-rates": "settings:read", "/settings/tokenfree/quota": "settings:read",
        },
        "POST": {
            "/stats/upstream-usage/sync": "finance:write", "/finance/daily/sync": "finance:write",
            "/tasks/{task_id}/cancel": "tasks:write", "/works/bulk": "works:review",
            "/templates": "templates:write", "/templates/bulk": "templates:write",
            "/settings/models/import-env": "settings:write", "/settings/upstream/models": "settings:write",
        },
        "PATCH": {
            "/works/{work_id}": "works:review", "/templates/{template_id}": "templates:write",
            "/settings/routing": "settings:write", "/settings/models": "settings:write",
            "/notifications/read": "notifications:read",
        },
        "DELETE": {"/templates/{template_id}": "templates:write"},
    }
    if path == "/api/health/details" and method == "GET":
        return frozenset({"tasks:read"})
    if not path.startswith("/api/admin"):
        return frozenset()
    path = path.removeprefix("/api/admin")
    if method == "PATCH" and path == "/users/{user_id}":
        return frozenset({"users:write", "users:role", "balance:write"})
    if method == "GET" and path in {
        "/projects", "/projects/{project_id}", "/drama-projects", "/drama-projects/{project_id}",
        "/drama-assets", "/drama-assets/{asset_id}", "/drama-episodes", "/drama-episodes/{episode_id}",
        "/drama-fragments", "/drama-fragments/{fragment_id}",
    }:
        return frozenset({"content:read"})
    permission = routes.get(method, {}).get(path)
    return frozenset({permission}) if permission else frozenset()
