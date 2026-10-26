import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type AdminOrder, type AdminStats, type AdminUpstreamUsage, type PageMeta } from "@/api/client";
import { useAdminRequest } from "./useAdminRequest";
import { hasPermission } from "@/lib/permissions";
import { buildStatsQuery, type DashboardFilterState } from "@/pages/dashboard/DashboardFilters";

/** 将 URL 中未知的枚举值恢复为默认值，避免无效统计请求。 */
function choice<T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(raw as T) ? raw as T : fallback;
}

/** 分别加载概览、近期订单与官方数据，让单个区块失败可以单独重试。 */
export function useDashboardData() {
  const [params, setParams] = useSearchParams();
  const section = choice(params.get("section"), ["overview", "usage", "finance", "projects"] as const, "overview");
  const filters: DashboardFilterState = {
    days: choice(params.get("days"), ["1", "7", "14", "30"] as const, "7"),
    domain: choice(params.get("domain"), ["all", "drama", "kepu", "api", "tools", "studio"] as const, "all"),
    capability: choice(params.get("capability"), ["all", "llm", "image", "video", "tts"] as const, "all"),
    metric: choice(params.get("metric"), ["charge", "cost", "calls"] as const, "charge"),
  };
  function setSection(next: typeof section) { const p = new URLSearchParams(params); p.set("section", next); setParams(p, { replace: true }); }
  function setFilters(next: DashboardFilterState) { const p = new URLSearchParams(params); Object.entries(next).forEach(([key, value]) => p.set(key, value)); setParams(p, { replace: true }); }
  const statsQuery = buildStatsQuery(section === "projects" ? { days: "30", domain: "all", capability: "all", metric: "charge" } : filters);
  const statsRequest = useAdminRequest<AdminStats>();
  const orderRequest = useAdminRequest<{ items: AdminOrder[]; meta: PageMeta }>();
  const upstreamRequest = useAdminRequest<AdminUpstreamUsage>();
  const { run: runStats } = statsRequest;
  const { run: runOrders } = orderRequest;
  const { run: runUpstream } = upstreamRequest;
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const loadStats = useCallback(() => runStats(async () => {
    const data = await api<AdminStats>(statsQuery);
    return data;
  }), [runStats, statsQuery]);
  const loadOrders = useCallback(() => runOrders(() => api<{ items: AdminOrder[]; meta: PageMeta }>("/api/admin/orders?page=1&page_size=8&status=paid")), [runOrders]);
  const loadUpstream = useCallback(() => runUpstream(() => api<AdminUpstreamUsage>("/api/admin/stats/upstream-usage?days=30")), [runUpstream]);
  useEffect(() => { void loadStats(); }, [loadStats]);
  useEffect(() => { if (statsRequest.data) setUpdatedAt(new Date().toLocaleTimeString()); }, [statsRequest.data]);
  useEffect(() => {
    if (section !== "finance") return;
    if (hasPermission("orders:read")) void loadOrders();
    if (hasPermission("finance:read")) void loadUpstream();
  }, [section, loadOrders, loadUpstream]);
  return { section, setSection, filters, setFilters, statsRequest, orderRequest, upstreamRequest, updatedAt, loadStats, loadOrders, loadUpstream };
}
