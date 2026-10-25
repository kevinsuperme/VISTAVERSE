"""抽取资产落库时 visualPrompt 须已含三视图等结构前缀。"""

from app.services.drama.generation_prompt import prompt_has_structure_prefix
from app.services.drama.seed_asset_params import (
    build_character_params,
    build_named_image_params,
    build_scene_params,
)


def test_build_character_params_includes_structure_prefix():
    params = build_character_params(
        {
            "name": "阿羽",
            "visualImage": "男性，二十岁，清瘦，羽甲短褐，眼神明亮",
            "title": "猎手",
        }
    )
    assert prompt_has_structure_prefix(params["visualPrompt"])
    assert "强制任务：角色设定板" in params["visualPrompt"]
    assert params["canvas"]["generation"]["prompt"] == params["visualPrompt"]


def test_build_scene_params_includes_structure_prefix():
    params = build_scene_params("治水营帐", "神话")
    assert prompt_has_structure_prefix(params["visualPrompt"])
    assert "强制任务：场景设计参考图" in params["visualPrompt"]


def test_build_prop_params_includes_structure_prefix():
    params = build_named_image_params("青铜短剑，刃口有缺口", "1:1", kind="prop")
    assert prompt_has_structure_prefix(params["visualPrompt"])
    assert "强制任务：道具设定板" in params["visualPrompt"]


def test_structure_prefix_not_duplicated():
    once = build_named_image_params("白玉令牌", "1:1", kind="prop")
    twice = build_named_image_params(once["visualPrompt"], "1:1", kind="prop")
    assert once["visualPrompt"].count("【强制任务：") == 1
    assert twice["visualPrompt"].count("【强制任务：") == 1
