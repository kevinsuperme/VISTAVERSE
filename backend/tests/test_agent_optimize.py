"""描述优化：台词与 @asset 不得被改写结果丢掉。"""

from app.services.agent.optimize import (
    extract_spoken_lines,
    finalize_optimized_prompt,
    restore_spoken_lines,
)


def test_extract_spoken_lines_from_say_and_braces():
    prompt = (
        "新角色站在门店前自拍。说 疯狂星期四 v我50 请你吃脆皮炸鸡。"
        "另一句 {欢迎光临}"
    )
    lines = extract_spoken_lines(prompt)
    assert "疯狂星期四 v我50 请你吃脆皮炸鸡" in lines
    assert "欢迎光临" in lines


def test_restore_spoken_lines_appends_missing_dialogue():
    original = "近景自拍，说 疯狂星期四 v我50 请你吃脆皮炸鸡"
    rewritten = "近景，角色正面朝镜头举起手机自拍，傍晚霓虹灯暖红光。"
    out = restore_spoken_lines(original, rewritten)
    assert "疯狂星期四 v我50 请你吃脆皮炸鸡" in out
    assert "说{" in out


def test_finalize_keeps_asset_and_dialogue():
    original = "@asset:12 站在门口，说 给我炸鸡"
    rewritten = "人物站在门口近景正面，暖光。"
    out = finalize_optimized_prompt(original, rewritten)
    assert "@asset:12" in out
    assert "给我炸鸡" in out
