"""按勾选 Skill 改写用户提示词，并保留 @asset 引用与台词。"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.runner import run_task_text

# ASSET_TOKEN_RE 画布/分镜里的资产引用
ASSET_TOKEN_RE = re.compile(r"@asset:\d+")
# 花括号台词：{疯狂星期四…}
BRACE_LINE_RE = re.compile(r"\{([^{}\n]{2,120})\}")
# 「说 / 说道 / 说着」后的口播正文
SAY_LINE_RE = re.compile(
    r"说(?:道|着)?[：:\s]+([「『\"“]?[^「」『』\"”\n。.!！？]{2,120}[」』\"”]?)",
)
# 角色名：台词（排除空镜/景别等画面标签）
COLON_LINE_RE = re.compile(
    r"(?<![空远中近特全景别镜头画面])([\u4e00-\u9fffA-Za-z0-9_·]{1,16})[：:]([^\n。.!！？]{2,120})",
)

VIDEO_OPTIMIZE_SYSTEM = """你是 Seedance 视频提示词导演。根据已启用的 Agent Skill，把用户提示词改写成更适合生成视频的中文画面描述。

硬性规则：
1. 只输出优化后的提示词正文，不要标题、解释、markdown 代码块、引号包裹。
2. 必须原样保留用户提示词里每一个 `@asset:数字` 引用，不得删除、改写、翻译或拆开。
3. 不要编造未出现的角色名或场景名；用 @asset 引用代替重复人名。
4. 保留用户原意（谁、在哪、做什么），按 Skill 补全第一帧、站位、视线、光位、镜头运动与物理接触。
5. 语言具体、可拍、简体中文。
6. 对白/台词/口播是核心内容，绝不能删掉或概括掉。凡原文出现的「说…」「角色名：…」「{台词}」「【对白】」等，台词正文必须原样保留；可写成「说{台词}」或「{台词}」，但字词不得改写、省略、翻译。
7. 优化只加强画面与镜头，不要把「有人说话」的提示词改成纯空镜。
"""

IMAGE_OPTIMIZE_SYSTEM = """你是画面提示词导演。根据已启用的 Agent Skill，把用户提示词改写成更适合生成静帧的中文画面描述。

硬性规则：
1. 只输出优化后的提示词正文，不要标题、解释、markdown 代码块、引号包裹。
2. 必须原样保留用户提示词里每一个 `@asset:数字` 引用，不得删除、改写、翻译或拆开。
3. 不要编造未出现的角色名或场景名；用 @asset 引用代替重复人名。
4. 保留用户原意，按 Skill 补全构图、光位、站位与视线。
5. 语言具体、可拍、简体中文。
6. 若原文含对白/台词字样，仍须保留台词正文，不得删掉。
"""


def extract_asset_tokens(prompt: str) -> list[str]:
    # 按出现顺序去重提取 @asset:id
    seen: set[str] = set()
    tokens: list[str] = []
    for match in ASSET_TOKEN_RE.finditer(prompt or ""):
        token = match.group(0)
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _normalize_line(text: str) -> str:
    return text.strip().strip("「」『』\"“”'").strip()


def extract_spoken_lines(prompt: str) -> list[str]:
    """从原文提取口播/对白正文（去重、保序）。"""
    seen: set[str] = set()
    lines: list[str] = []

    def add(raw: str) -> None:
        text = _normalize_line(raw)
        if len(text) < 2 or text in seen:
            return
        # 跳过纯画面标签误伤
        if text.startswith(("空镜", "远景", "近景", "中景", "特写", "全景")):
            return
        seen.add(text)
        lines.append(text)

    for match in BRACE_LINE_RE.finditer(prompt or ""):
        add(match.group(1))
    for match in SAY_LINE_RE.finditer(prompt or ""):
        add(match.group(1))
    for match in COLON_LINE_RE.finditer(prompt or ""):
        speaker = match.group(1).strip()
        if speaker in {"空镜", "远景", "近景", "中景", "特写", "全景", "画面", "镜头"}:
            continue
        add(match.group(2))
    return lines


def strip_optimize_fences(text: str) -> str:
    # 去掉模型偶尔包上的代码块
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip().strip('"').strip("“”")


def restore_asset_tokens(original: str, rewritten: str) -> str:
    # 模型漏掉的 @asset 引用补回文末
    text = strip_optimize_fences(rewritten)
    missing = [token for token in extract_asset_tokens(original) if token not in text]
    if missing:
        text = f"{text.rstrip()} {' '.join(missing)}".strip()
    return text


def restore_spoken_lines(original: str, rewritten: str) -> str:
    """模型漏掉的台词补回文末，写成 说{台词}。"""
    text = strip_optimize_fences(rewritten)
    missing = [line for line in extract_spoken_lines(original) if line not in text]
    if not missing:
        return text
    extras = " ".join(f"说{{{line}}}" for line in missing)
    return f"{text.rstrip()} {extras}".strip()


def finalize_optimized_prompt(original: str, rewritten: str) -> str:
    # 先补 @asset，再补台词
    return restore_spoken_lines(original, restore_asset_tokens(original, rewritten))


def system_prompt_for_task(task: str) -> str:
    # 按任务选优化系统提示
    if task == "image_prompt":
        return IMAGE_OPTIMIZE_SYSTEM
    return VIDEO_OPTIMIZE_SYSTEM


async def optimize_prompt_with_skills(
    db: AsyncSession,
    user_id: int,
    *,
    prompt: str,
    skill_ids: list[int],
    task: str = "video_prompt",
) -> str:
    """用勾选 Skill 改写提示词；空 skill 时原样返回。"""
    source = (prompt or "").strip()
    if not source:
        return ""
    if not skill_ids:
        return source
    rewritten = await run_task_text(
        db,
        user_id,
        task=task,
        system=system_prompt_for_task(task),
        user=(
            "请优化下面提示词。务必保留其中的对白/台词原文与所有 @asset 引用。\n\n"
            f"{source}"
        ),
        temperature=0.4,
        max_tokens=2048,
        skill_ids=skill_ids,
    )
    return finalize_optimized_prompt(source, rewritten)
