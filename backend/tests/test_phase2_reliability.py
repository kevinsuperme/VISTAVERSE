"""第二阶段可靠性回归：持久任务 handler 与动态认证配置。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_studio_image_handler_delegates_to_persistent_executor(monkeypatch) -> None:
    from app.services.tasks import handlers

    seen: list[int] = []

    async def fake_execute(task):
        seen.append(int(task.id))
        return {"ok": True, "run_id": 7}

    monkeypatch.setattr("app.services.studio_tools.execute_image_tool_task", fake_execute)
    handler = handlers.get_task_handler("studio", "tool_image")
    assert handler is not None

    result = await handler.executor(SimpleNamespace(id=42))

    assert result == {"ok": True, "run_id": 7}
    assert seen == [42]


def test_auth_uses_current_settings_for_token_decode(monkeypatch) -> None:
    from app.services import auth

    settings = SimpleNamespace(secret_key="phase2-secret-a", access_token_expire_minutes=10)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    token = auth.create_access_token("123")
    assert auth.decode_token(token) == "123"

    settings.secret_key = "phase2-secret-b"
    assert auth.decode_token(token) is None


@pytest.mark.asyncio
async def test_admin_balance_patch_selects_user_for_update() -> None:
    from app.api.admin.users import patch_user
    from app.schemas import AdminUserPatch

    target = SimpleNamespace(
        id=9,
        email="target@example.com",
        nickname="target",
        quota_left=0,
        balance_fen=100,
        frozen_fen=0,
        plan="free",
        role="user",
        phone="",
        created_at=None,
    )
    admin = SimpleNamespace(id=1, role="admin")
    statements = []

    class Result:
        def scalar_one_or_none(self):
            return target

    class FakeDb:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

        def add(self, _row):
            pass

        async def commit(self):
            pass

        async def refresh(self, _row):
            pass

    out = await patch_user(
        user_id=target.id,
        body=AdminUserPatch(balance_delta_fen=50, balance_note="回归测试"),
        admin=admin,
        db=FakeDb(),
    )

    assert out.balance_fen == 150
    assert statements and statements[0]._for_update_arg is not None
