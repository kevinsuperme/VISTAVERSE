"""Typed, nonempty API fixtures for browser acceptance; no real backend is used."""
from copy import deepcopy
from pathlib import Path
import re

STAMP = "2026-10-25T10:00:00Z"
USER = dict(id=1, email="fixture@example.test", nickname="验收用户", phone="", quota_left=8, balance_fen=12345, frozen_fen=100, plan="pro", role="user", created_at=STAMP)
AUTH = {**USER, "id": 99, "role": "admin", "permissions": []}
USAGE = dict(charge_fen=230, cost_fen=100, tokens=5000, calls=5, image_gens=2, video_gens=1, llm_calls=1, tts_gens=1)
PROJECT = dict(id=1, user_id=1, user_email=USER["email"], template_id="fixture_template", title="验收科普项目", status="completed", progress=100, cover_url="", final_video_url="", pipeline_mode="auto", created_at=STAMP, updated_at=STAMP, shot_count=1, usage=USAGE, shots=[dict(id=1, shot_no=1, status="completed", has_image=True, has_video=True, has_audio=True, duration=5)], recent_tasks=[])
DRAMA = dict(id=1, user_id=1, user_email=USER["email"], title="验收漫剧项目", description="完整 fixture 数据", created_at=STAMP, updated_at=STAMP, episode_count=1, asset_count=1, fragment_count=1, summary_status="succeeded", usage=USAGE, episodes=[dict(id=1, name="第一集", fragment_count=1)], assets=[dict(id=1, type="character", name="验收角色", has_cover=False)], recent_tasks=[])
ASSET = dict(id=1, project_id=1, project_title=DRAMA["title"], user_id=1, user_email=USER["email"], type="character", asset_type="image", name="验收角色", cover="", url="", has_cover=False, generation_status="succeeded", created_at=STAMP, updated_at=STAMP, params={"prompt": "fixture character"})
FRAGMENT = dict(id=1, episode_id=1, episode_name="第一集", project_id=1, project_title=DRAMA["title"], user_id=1, user_email=USER["email"], sort_order=1, content="验收分镜内容", cover="", video="", duration_sec=5, generation_status="succeeded", asset_ref_count=1, created_at=STAMP, updated_at=STAMP, params={}, asset_ids=[1])
EPISODE = dict(id=1, project_id=1, project_title=DRAMA["title"], user_id=1, user_email=USER["email"], name="第一集", fragment_count=1, fragment_plan_status="succeeded", created_at=STAMP, updated_at=STAMP, fragments=[FRAGMENT])
WORK = dict(id=1, project_id=1, user_id=1, user_email=USER["email"], title="验收作品", cover_url="", video_url="", visibility="public", audit_status="pending", audit_reason="", audited_by=None, audited_at=None, published_at=STAMP)
TEMPLATE = dict(id="fixture_template", name="验收模板", description="完整模板 fixture", category=["电影感"], preview_cover="", style_prefix="cinematic", negative_prompt="", default_ratio="16:9", shot_duration_min=3, shot_duration_max=8, llm_system_addon="", seedream_config={"character_prompt": "character"}, seedance_config={}, audio_config={}, subtitle_config={}, sort_order=0, is_active=True, is_premium=True)
ORDER = dict(id=1, out_trade_no="FIXTURE_ORDER_001", user_id=1, user_email=USER["email"], sku_id="balance_10", amount_fen=1000, credit_fen=1000, pay_type="alipay", status="paid", trade_no="FIXTURE_TRADE_001", created_at=STAMP, paid_at=STAMP)
LEDGER = dict(id=1, user_id=1, user_email=USER["email"], delta_fen=1000, balance_after=12345, kind="recharge", ref_type="order", ref_id="1", note="验收流水", created_at=STAMP, operator_email="admin@example.test")
EVENT = dict(id=1, user_id=1, user_email=USER["email"], task_run_id=1, domain="science", capability="text", billing_key="llm", model="kimi-k2.6", total_tokens=1000, charge_fen=10, cost_fen=5, estimated=False, billing_basis="tokens", billing_basis_label="Token", created_at=STAMP, task_status="succeeded", project_id=1, provider="tokenfree")
TASK = dict(id=1, domain="science", task_type="project_generate", status="succeeded", priority=0, requested_by=1, user_email=USER["email"], progress_percent=100, cancel_requested=False, cancelable=False, created_at=STAMP, started_at=STAMP, finished_at=STAMP, updated_at=STAMP, project_id=1, billing_estimate_fen=100, billing_charged_fen=100, billing_refunded_fen=0, billing_status="settled", payload={"prompt": "fixture"}, result_payload={}, steps=[], events=[], targets=[], usage_lines=[EVENT], events_total=0, upstream_events=[], upstream_events_total=0)
TASK_STATS = dict(pending_count=1, pending_ready_count=1, pending_deferred_count=0, pending_delayed_count=0, oldest_ready_wait_sec=3, active_count=1, leased_count=0, running_count=1, awaiting_poll_count=0, cancel_requested_count=0, succeeded_count=10, failed_count=1, cancelled_count=0, scheduler_running_jobs=1, max_concurrency=4, scheduler="running", poller="running", watchdog="running", runtime_healthy=True, scheduler_consecutive_failures=0, domains=[dict(domain="science", pending=1, active=1, succeeded=10, failed=1, cancelled=0)], fetched_at=STAMP)
STATS = dict(user_count=31, order_paid_total_fen=100000, order_paid_today_fen=2000, project_status_counts={"completed": 2, "failed": 1}, drama_project_count=2, usage_calls_today=5, usage_calls_month=20, usage_calls_total=30, usage_charge_today_fen=100, usage_charge_month_fen=200, usage_charge_total_fen=300, usage_cost_today_fen=50, usage_cost_month_fen=100, usage_cost_total_fen=150, usage_by_capability=[dict(key="text", calls=2, charge_fen=100, cost_fen=50)], usage_by_domain=[dict(key="science", calls=2, charge_fen=100, cost_fen=50)], daily_usage=[dict(date="2026-10-25", calls=2, charge_fen=100, cost_fen=50)], top_users_by_charge=[dict(user_id=1, email=USER["email"], calls=2, charge_fen=100, cost_fen=50)])
FINANCE_ROW = dict(date="2026-10-25", charge_fen=1000, cost_fen=400, tokens=2000, actual_cost_fen=350, profit_fen=650, profit_pct=65)
ROUTING = dict(system_channels=[dict(id="tokenfree", name="TokenFree New API", base_url="https://www.cattoken.vip/v1", api_key="", has_api_key=True, api_format="openai", protocol="auto", models=["kimi-k2.6"], enabled=True, sort_order=0)], logical_models=[], default_models=dict(text_model="kimi-k2.6", image_model="seedream-5.0-pro", video_model="seedance-2.5", audio_model="qwen-tts-2025-05-22"), validation_errors=[], updated_at=STAMP)


def model_settings():
    """Materialize every primitive in the checked-in contract, plus typed readiness."""
    source = (Path(__file__).parents[1] / "src/api/types/settings.ts").read_text(encoding="utf-8")
    source = source.split("export type AdminModelSettings = {", 1)[1].split("\n};", 1)[0]
    result = {}
    for name, kind in re.findall(r"^\s+(\w+)\??: (string|number|boolean)", source, re.M):
        result[name] = {"string": "", "number": 1, "boolean": False}[kind]
    result.update(oss_endpoint="oss-cn-beijing.aliyuncs.com", oss_region="cn-beijing", oss_bucket="fixture", oss_enabled=True, has_oss_access_key_id=True, has_oss_access_key_secret=True, public_base_url="https://example.test", ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", source="db", seedance_duration_min=3, seedance_duration_max=8, ark_video_poll_interval=1, ark_video_poll_timeout=60, smtp_port=587, readiness=[dict(capability="text", label="文本", model="kimi-k2.6", ready=True, message="已配置")], updated_at=STAMP)
    return result


COLLECTIONS = {"users": USER, "orders": ORDER, "ledger": LEDGER, "usage-events": EVENT, "projects": PROJECT, "drama-projects": DRAMA, "drama-assets": ASSET, "drama-episodes": EPISODE, "drama-fragments": FRAGMENT, "works": WORK, "templates": TEMPLATE, "tasks": TASK}


def paged(item, query, total=31):
    return {"items": [deepcopy(item)], "meta": {"page": int(query.get("page", [1])[0]), "page_size": int(query.get("page_size", [10])[0]), "total": total}}
