"""seedream_text_soften 单元测试。"""
from __future__ import annotations

from app.services.drama.generation_prompt import (
    CHARACTER_PROMPT_PREFIX,
    build_generation_prompt,
    ensure_structure_in_prompt,
)
from app.services.seedream_text_soften import (
    compact_seedream_prompt_for_retry,
    soften_seedream_input_text,
    style_only_seedream_prompt_for_retry,
)


def test_soften_preserves_turnaround_prefix() -> None:
    raw = "盛唐顶流，白衣佩剑，腰悬酒葫芦，身份：诗仙。电影质感。"
    # 三视图须先写入正文（提示词框），提交时不再静默拼接
    full = ensure_structure_in_prompt(raw, "character")
    soft = soften_seedream_input_text(full)
    assert soft.startswith(CHARACTER_PROMPT_PREFIX) or "全身三视图" in soft
    assert "正面全身站姿" in soft
    assert "左侧面全身站姿" in soft
    assert "背面全身站姿" in soft
    assert "诗仙" not in soft
    assert "酒葫芦" not in soft
    assert "盛唐" not in soft


def test_build_generation_prompt_does_not_auto_prepend_structure() -> None:
    raw = "黑发少女，白衣。"
    out = build_generation_prompt(raw, asset_type="character")
    assert out == raw or out.startswith(raw)
    assert "全身三视图" not in out
    with_struct = ensure_structure_in_prompt(raw, "character")
    assert with_struct.startswith(CHARACTER_PROMPT_PREFIX)
    assert "黑发少女" in with_struct


def test_soften_xiaoxuesheng_and_child_terms() -> None:
    raw = (
        "毛毡教室剪影，课桌后坐着齐刷刷毛毡小人，穿着现代校服，"
        "身份：现代课堂学生。标签：传承+童声+童真"
    )
    out = soften_seedream_input_text(raw)
    assert "小学生" not in out
    assert "童声" not in out
    assert "校服" not in out
    assert "课堂" not in out
    assert "学生" not in out


def test_compact_retry_keeps_turnaround() -> None:
    full = (
        "【强制任务：角色设定板构图】很长前缀。"
        "请严格依据以下用户描述生成上述结构的角色设定图："
        "盛唐顶流，白衣佩剑，腰悬酒葫芦，身份：诗仙。电影质感。"
    )
    compact = compact_seedream_prompt_for_retry(full)
    assert "三视图" in compact
    assert "正面" in compact and "背面" in compact
    assert "酒葫芦" not in compact
    assert "诗仙" not in compact
    assert "盛唐" not in compact


def test_style_only_keeps_turnaround_and_felt() -> None:
    raw = "盛唐顶流，白衣佩剑，腰悬酒葫芦，身份：诗仙。羊毛毡 / 毛毡定格，粘土软萌。"
    out = style_only_seedream_prompt_for_retry(raw)
    assert "三视图" in out
    assert "诗仙" not in out
    assert "盛唐" not in out
    assert "酒" not in out
    assert "白衣" in out
    assert "羊毛毡" in out or "毛毡" in out
