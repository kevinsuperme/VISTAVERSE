"""Real Chromium acceptance against API FIXTURES, never a real backend.

Usage: python admin/tests/browser_acceptance.py [--base-url http://127.0.0.1:5174]
Requires system Python playwright + an installed Chrome. Artifacts stay in .tmp.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect
from browser_fixtures import AUTH, COLLECTIONS, FINANCE_ROW, ROUTING, STAMP, STATS, TASK_STATS, TEMPLATE, model_settings, paged

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".tmp/admin-acceptance"
ROUTES = ["/", "/users", "/orders", "/orders?tab=ledger", "/orders?tab=usage", "/adjustments", "/finance", "/projects", "/drama-projects", "/drama-projects/1", "/drama-assets", "/drama-assets/1", "/drama-episodes", "/drama-episodes/1", "/drama-fragments", "/drama-fragments/1", "/works", "/templates", "/queues", "/settings?tab=routing", "/settings?tab=runtime", "/settings?tab=oss", "/settings?tab=payment", "/settings?tab=site"]


class MockAPI:
    def __init__(self):
        self.auth = deepcopy(AUTH)
        self.models = model_settings()
        self.routing = deepcopy(ROUTING)
        self.template = deepcopy(TEMPLATE)
        self.requests = []
        self.unknown = []
        self.failures = {}
        self.read_ids = set()
        self.bulk_partial = False
        self.expected_failure_paths = set()

    def fail_once(self, method, path):
        self.expected_failure_paths.add(path)
        self.failures[(method, path)] = self.failures.get((method, path), 0) + 1

    def fail_until_released(self, method, path):
        self.expected_failure_paths.add(path)
        self.failures[(method, path)] = -1

    def handle(self, route):
        request = route.request
        parsed = urlparse(request.url)
        path, method, query = parsed.path, request.method, parse_qs(parsed.query)
        payload = json.loads(request.post_data) if request.post_data else None
        self.requests.append(dict(method=method, path=path, query=query, payload=payload))
        failure = (method, path)
        if self.failures.get(failure, 0):
            if self.failures[failure] > 0: self.failures[failure] -= 1
            return route.fulfill(status=500, json={"detail": "FIXTURE 可重试错误"})
        result = None
        if path == "/api/auth/me": result = self.auth
        elif path == "/api/admin/notifications/read": self.read_ids.update(payload["ids"]); result = {"ok": True}
        elif path == "/api/admin/notifications":
            notification = dict(id="fixture-notification", kind="work_pending", severity="warning", title="验收待审核作品", message="这是一条 fixture 通知", href="/works?work=1", created_at=STAMP, read="fixture-notification" in self.read_ids)
            result = paged(notification, query, 1)
            result["unread_count"] = 0 if notification["read"] else 1
            if query.get("unread_only") == ["true"] and notification["read"]: result["items"] = []; result["meta"]["total"] = 0
        elif path == "/api/admin/settings/models":
            if method == "PATCH":
                self.models.update({key: value for key, value in payload.items() if not key.startswith("clear_") and "secret" not in key and "password" not in key and "key" not in key})
                result = {"settings": self.models, "ok": True, "applied_fields": list(payload)}
            else: result = self.models
        elif path == "/api/admin/settings/routing": result = self.routing if method == "GET" else {"settings": self.routing, "ok": True, "applied": []}
        elif path == "/api/admin/templates/meta": result = {"categories": ["电影感"], "category_counts": {"电影感": 31}, "total": 31}
        elif path == "/api/admin/templates/bulk":
            results = [dict(id=identifier, success=not self.bulk_partial, **({"error": "FIXTURE 项目拒绝"} if self.bulk_partial else {})) for identifier in payload["ids"]]
            result = dict(results=results, succeeded=sum(item["success"] for item in results), failed=sum(not item["success"] for item in results))
        elif path.endswith("/export"):
            return route.fulfill(status=200, content_type="text/csv; charset=utf-8", body="id,name\nfixture_template,Fixture\n", headers={"Content-Disposition": 'attachment; filename="fixture.csv"'})
        elif path == "/api/admin/stats": result = STATS
        elif path == "/api/admin/stats/upstream-usage": result = dict(configured=True, days=30, last_sync_at=STAMP, series=[dict(date="2026-10-25", local_cost_fen=50, local_tokens=1000, official_tokens=1000, official_cost_fen=50, delta_fen=0, delta_pct=0)])
        elif path == "/api/admin/finance/daily": result = dict(configured=True, days=int(query.get("days", [30])[0]), last_sync_at=STAMP, totals=FINANCE_ROW, series=[FINANCE_ROW])
        elif path == "/api/admin/tasks/stats": result = TASK_STATS
        elif re.fullmatch(r"/api/admin/tasks/\d+/events", path): result = dict(items=[], total=0, page=1, page_size=20)
        else:
            matched = re.fullmatch(r"/api/admin/([^/]+)(?:/([^/]+))?", path)
            if matched and matched[1] in COLLECTIONS:
                resource, identifier = matched.groups()
                item = self.template if resource == "templates" else COLLECTIONS[resource]
                if identifier: result = deepcopy(item)
                else: result = paged(item, query)
                if resource == "users" and query.get("q"): result["items"] = [deepcopy(COLLECTIONS["users"])]
        if result is None:
            self.unknown.append(dict(method=method, path=path, query=query))
            return route.fulfill(status=501, json={"detail": f"Unspecified fixture contract: {method} {path}"})
        return route.fulfill(status=200, json=result)


class Acceptance:
    def __init__(self, browser, base_url, widths):
        self.browser, self.base_url, self.widths = browser, base_url.rstrip("/"), widths
        self.api = MockAPI()
        self.results, self.page_errors, self.console_errors, self.expected_console_errors = [], [], [], []
        self.context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        self.context.add_init_script("localStorage.setItem('admin_token','fixture-token');")
        # A broad **/api/** would also intercept Vite's /src/api/client.ts.
        self.context.route(re.compile(r"https?://[^/]+/api/"), self.api.handle)
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("console", self.capture_console)
        self.page.set_default_timeout(7000)

    def capture_console(self, message):
        if message.type != "error": return
        entry = {"text": message.text, "url": message.location.get("url", "")}
        if "Failed to load resource" in message.text and urlparse(entry["url"]).path in self.api.expected_failure_paths:
            self.expected_console_errors.append(entry)
        else: self.console_errors.append(entry)

    def go(self, route):
        self.page.goto(self.base_url + route, wait_until="networkidle")
        self.page.locator(".admin-content").wait_for()
        expect(self.page.locator(".admin-content")).not_to_contain_text("页面出现异常")

    def check_layout(self):
        dimensions = self.page.evaluate("""() => ({viewport:innerWidth, document:document.documentElement.scrollWidth, offenders:[...document.querySelectorAll('.admin-content *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+2 && getComputedStyle(e).position!=='fixed' && !e.closest('.admin-data-table,.admin-table-wrap,.admin-detail-table-wrap,[role=group]')}).slice(0,8).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,60)}))})""")
        assert dimensions["document"] <= dimensions["viewport"] + 2, dimensions
        return dimensions

    def run_case(self, name, action):
        started, error_index = time.monotonic(), len(self.page_errors)
        result = {"name": name}
        try:
            detail = action()
            assert len(self.page_errors) == error_index, self.page_errors[error_index:]
            result.update(status="passed", detail=detail)
        except Exception as error:
            result.update(status="failed", error=str(error))
        result["seconds"] = round(time.monotonic() - started, 2)
        self.results.append(result)
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        self.page.screenshot(path=str(ARTIFACTS / f"{safe}.png"), full_page=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    def matrix(self):
        for width in self.widths:
            self.page.set_viewport_size({"width": width, "height": 1000 if width > 768 else 900})
            for route in ROUTES:
                self.run_case(f"layout-{width}-{route}", lambda route=route: (self.go(route), self.check_layout())[1])

    def interactions(self):
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        self.run_case("drawer-work-deeplink-retry", self.drawer_retry)
        self.run_case("drawer-user-deeplink", self.user_drawer)
        self.run_case("drawer-order-deeplink", self.order_drawer)
        self.run_case("drawer-task-deeplink", self.task_drawer)
        self.run_case("search-pagination-url", self.search_pagination)
        self.run_case("same-event-url-updates", self.same_event_urls)
        self.run_case("drawer-preserves-list-context", self.drawer_context)
        self.run_case("user-search-keyboard-combobox", self.user_combobox)
        self.run_case("settings-load-retry", self.settings_load_retry)
        self.run_case("settings-secret-failure-dirty-tab", self.settings_secret)
        self.run_case("settings-dirty-sidebar-and-back", self.settings_navigation)
        self.run_case("templates-premium-bulk-export", self.template_bulk)
        self.run_case("notification-read-persistence", self.notifications)
        self.run_case("role-route-and-write-blocking", self.roles)
        self.run_case("mobile-navigation-focus-and-layout", self.mobile_navigation)
        self.run_case("mobile-drawer-deeplink-retry", self.drawer_retry)

    def drawer_retry(self):
        self.api.fail_until_released("GET", "/api/admin/works/1")
        self.go("/works?work=1")
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role("alert")).to_contain_text("FIXTURE")
        self.api.failures[("GET", "/api/admin/works/1")] = 0
        dialog.get_by_role("button", name="重试", exact=True).click()
        expect(dialog.get_by_role("heading", name="验收作品")).to_be_visible()
        assert "work=1" in self.page.url
        assert "admin-drawer" in dialog.get_attribute("class")
        self.page.reload(wait_until="networkidle")
        expect(self.page.get_by_role("dialog")).to_be_visible()
        self.page.get_by_role("button", name="关闭对话框", exact=True).click()
        expect(self.page.get_by_role("dialog")).to_have_count(0)
        assert "work=" not in self.page.url
        return self.check_layout()

    def user_drawer(self):
        self.go("/users?user=1")
        dialog = self.page.get_by_role("dialog")
        expect(dialog.get_by_role("heading", name="用户明细")).to_be_visible()
        expect(dialog).to_contain_text("fixture@example.test")
        dialog.get_by_role("tab", name="最近订单").click()
        expect(dialog).to_contain_text("FIXTURE_ORDER_001")
        return self.check_layout()

    def order_drawer(self):
        self.go("/orders?order=1")
        expect(self.page.get_by_role("dialog")).to_contain_text("FIXTURE_ORDER_001")
        return self.check_layout()

    def task_drawer(self):
        self.go("/queues?task=1")
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text("fixture")
        return self.check_layout()

    def search_pagination(self):
        self.go("/works")
        field = self.page.locator(".admin-filter-search input").first
        field.fill("验收")
        field.press("Enter")
        self.page.wait_for_timeout(200)
        assert parse_qs(urlparse(self.page.url).query).get("q") == ["验收"], self.page.url
        self.page.get_by_role("button", name="第 2 页", exact=True).click()
        expect(self.page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")
        assert parse_qs(urlparse(self.page.url).query).get("page") == ["2"]
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator(".admin-filter-search input").first).to_have_value("验收")
        assert any(request["path"] == "/api/admin/works" and request["query"].get("q") == ["验收"] and request["query"].get("page") == ["2"] for request in self.api.requests)

    def settings_load_retry(self):
        self.api.fail_until_released("GET", "/api/admin/settings/models")
        self.go("/settings?tab=oss")
        expect(self.page.get_by_role("alert")).to_contain_text("FIXTURE")
        self.api.failures[("GET", "/api/admin/settings/models")] = 0
        self.page.get_by_role("button", name="重新加载", exact=True).click()
        expect(self.page.get_by_text("AccessKey Secret", exact=True)).to_be_visible()

    def same_event_urls(self):
        for route in ["/users?page=2&q=fixture", "/queues?page=2&domain=science"]:
            self.go(route)
            if route.startswith("/users"):
                self.page.locator(".admin-pagination select").select_option("20")
                self.page.wait_for_timeout(150)
            query = parse_qs(urlparse(self.page.url).query)
            if route.startswith("/users"): assert query.get("page_size") == ["20"], self.page.url
            if route.startswith("/users"): assert query.get("page", ["1"]) == ["1"], self.page.url
            if route.startswith("/users"): assert query.get("q") == ["fixture"], self.page.url
            else: assert query.get("domain") == ["science"], self.page.url
            self.page.reload(wait_until="networkidle")
            if route.startswith("/users"): expect(self.page.locator(".admin-pagination select")).to_have_value("20")
        self.go("/queues?page=2&domain=science&page_size=20")
        self.page.locator("select").nth(1).select_option("failed")
        self.page.wait_for_timeout(150)
        query = parse_qs(urlparse(self.page.url).query)
        assert query.get("status") == ["failed"] and query.get("page", ["1"]) == ["1"] and query.get("domain") == ["science"] and query.get("page_size") == ["20"], self.page.url

    def drawer_context(self):
        self.go("/works?page=2&q=fixture&work=1")
        expect(self.page.get_by_role("dialog")).to_contain_text("验收作品")
        self.page.get_by_role("button", name="关闭对话框", exact=True).click()
        query = parse_qs(urlparse(self.page.url).query)
        assert query.get("q") == ["fixture"] and query.get("page") == ["2"] and "work" not in query, self.page.url
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator(".admin-filter-search input").first).to_have_value("fixture")
        expect(self.page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")

    def user_combobox(self):
        self.go("/works")
        field = self.page.get_by_role("combobox", name="搜索用户邮箱 / 账号 ID", exact=True)
        field.fill("fixture")
        expect(self.page.get_by_role("option", name=re.compile("fixture@example.test"))).to_be_visible()
        field.press("ArrowDown")
        assert field.get_attribute("aria-activedescendant")
        field.press("Enter")
        expect(self.page.get_by_role("listbox")).to_have_count(0)
        self.page.get_by_role("button", name="清除用户", exact=True).click()
        expect(field).to_have_value("")

    def settings_navigation(self):
        self.go("/works")
        self.page.get_by_role("link", name="系统设置", exact=True).click()
        expect(self.page.get_by_role("heading", name="系统设置", level=2)).to_be_visible()
        field = self.page.locator('input[type="password"]').first
        field.fill("fixture-unsaved-routing-key")
        self.page.get_by_role("link", name="模板管理", exact=True).click()
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_contain_text("离开并放弃")
        dialog.get_by_role("button", name="取消", exact=True).click()
        expect(field).to_have_value("fixture-unsaved-routing-key")
        self.page.evaluate("history.back()")
        expect(self.page.get_by_role("dialog")).to_contain_text("离开并放弃")
        self.page.get_by_role("dialog").get_by_role("button", name="取消", exact=True).click()
        expect(field).to_have_value("fixture-unsaved-routing-key")
        self.page.get_by_role("link", name="模板管理", exact=True).click()
        self.page.get_by_role("dialog").get_by_role("button", name="放弃修改并离开", exact=True).click()
        self.page.wait_for_url("**/templates")

    def settings_secret(self):
        self.go("/settings?tab=oss")
        fields = self.page.locator('input[type="password"]')
        fields.nth(0).fill("fixture-key")
        fields.nth(1).fill("fixture-secret-never-real")
        expect(self.page.get_by_role("status")).to_contain_text("未保存")
        self.api.fail_once("PATCH", "/api/admin/settings/models")
        self.page.get_by_role("button", name="保存", exact=True).click()
        expect(fields.nth(1)).to_have_value("fixture-secret-never-real")
        expect(self.page.get_by_role("status")).to_contain_text("修改已保留")
        self.page.get_by_role("tab", name="运行参数", exact=True).click()
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_contain_text("放弃未保存")
        dialog.get_by_role("button", name="取消", exact=True).click()
        expect(fields.nth(1)).to_have_value("fixture-secret-never-real")
        self.page.get_by_role("button", name="保存", exact=True).click()
        expect(fields.nth(1)).to_have_value("")
        expect(self.page.get_by_role("status")).to_contain_text("已保存")
        self.page.get_by_role("tab", name="运行参数", exact=True).click()
        expect(self.page.get_by_role("dialog")).to_have_count(0)
        assert "tab=runtime" in self.page.url

    def template_bulk(self):
        self.go("/templates?status=premium")
        assert any(request["path"] == "/api/admin/templates" and request["query"].get("is_premium") == ["true"] for request in self.api.requests)
        self.page.get_by_role("checkbox", name="全选当前页", exact=True).check()
        self.api.bulk_partial = True
        self.page.get_by_role("button", name="批量下架", exact=True).click()
        self.page.get_by_role("dialog").get_by_role("button", name="确认", exact=True).click()
        expect(self.page.get_by_role("alert").filter(has_text="失败项已保留选择")).to_be_visible()
        expect(self.page.get_by_role("checkbox", name="选择模板 验收模板", exact=True)).to_be_checked()
        self.api.bulk_partial = False
        self.page.get_by_role("button", name="批量上架", exact=True).click()
        self.page.get_by_role("dialog").get_by_role("button", name="确认", exact=True).click()
        expect(self.page.get_by_role("checkbox", name="选择模板 验收模板", exact=True)).not_to_be_checked()
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="导出 CSV", exact=True).click()
        artifact = download.value
        artifact.save_as(str(ARTIFACTS / "fixture-export.csv"))
        assert artifact.failure() is None
        assert any(request["path"] == "/api/admin/templates/export" and request["query"].get("is_premium") == ["true"] for request in self.api.requests)

    def notifications(self):
        self.go("/works")
        self.page.get_by_role("button", name=re.compile("^通知中心")).click()
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_contain_text("验收待审核作品")
        dialog.get_by_role("button", name="本页标记已读", exact=True).click()
        expect(dialog.locator(".admin-notifications li")).to_have_class("is-read")
        self.page.reload(wait_until="networkidle")
        self.page.get_by_role("button", name="通知中心", exact=True).click()
        expect(self.page.get_by_role("dialog").locator(".admin-notifications li")).to_have_class("is-read")

    def roles(self):
        self.api.auth = {**AUTH, "role": "admin_readonly", "permissions": ["users:read", "works:read", "templates:read", "settings:read"]}
        self.go("/users")
        expect(self.page.get_by_role("button", name="角色", exact=True)).to_have_count(0)
        self.go("/templates")
        expect(self.page.get_by_role("button", name="新建模板", exact=True)).to_have_count(0)
        expect(self.page.get_by_role("switch").first).to_be_disabled()
        self.go("/settings?tab=oss")
        expect(self.page.get_by_role("button", name="保存", exact=True)).to_have_count(0)
        expect(self.page.locator('input[type="password"]').first).to_be_disabled()
        self.go("/finance")
        expect(self.page.get_by_role("heading", name="没有访问权限", exact=True)).to_be_visible()
        self.api.auth = deepcopy(AUTH)

    def mobile_navigation(self):
        self.page.set_viewport_size({"width": 375, "height": 900})
        self.go("/works")
        trigger = self.page.get_by_role("button", name="打开导航菜单", exact=True)
        trigger.click()
        dialog = self.page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        rect = dialog.bounding_box()
        assert rect["x"] >= -1 and rect["width"] <= 375, rect
        self.page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(trigger).to_be_focused()
        trigger.click()
        self.page.get_by_role("dialog").get_by_role("link", name="模板管理", exact=True).click()
        expect(self.page.get_by_role("dialog")).to_have_count(0)
        assert "/templates" in self.page.url
        return self.check_layout()

    def finish(self):
        report = dict(mode="Real Chromium with explicit API fixtures; not real-backend integration", cases=self.results, page_errors=self.page_errors, console_errors=self.console_errors, expected_injected_failure_console_errors=self.expected_console_errors, unknown_api_contracts=self.api.unknown, request_count=len(self.api.requests))
        report["passed"] = sum(case["status"] == "passed" for case in self.results)
        report["failed"] = sum(case["status"] == "failed" for case in self.results)
        (ARTIFACTS / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Log request shapes, never test secret payloads.
        (ARTIFACTS / "requests.json").write_text(json.dumps([{key: value for key, value in request.items() if key != "payload"} for request in self.api.requests], ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: report[key] for key in ["passed", "failed", "page_errors", "console_errors", "unknown_api_contracts"]}, ensure_ascii=False), flush=True)
        self.context.close()
        return report["failed"] == 0 and not self.page_errors and not self.console_errors and not self.api.unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5174")
    parser.add_argument("--chrome", default="C:/Program Files/Google/Chrome/Application/chrome.exe")
    parser.add_argument("--widths", default="1440,768,375")
    parser.add_argument("--interactions-only", action="store_true")
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chrome, headless=True)
        acceptance = Acceptance(browser, args.base_url, [int(width) for width in args.widths.split(",")])
        if not args.interactions_only: acceptance.matrix()
        acceptance.interactions()
        passed = acceptance.finish()
        browser.close()
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__": main()
