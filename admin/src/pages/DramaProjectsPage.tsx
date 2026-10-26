import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, type AdminDramaProject, type PageMeta } from "@/api/client";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminUserSearchSelect } from "@/components/admin/AdminUserSearchSelect";
import { PaginationBar } from "@/components/PaginationBar";
import { DEFAULT_PAGE_SIZE } from "@/lib/pagination";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page";
import { fenToYuan } from "@/lib/utils";

type ListRes = { items: AdminDramaProject[]; meta: PageMeta };

/** 漫剧项目列表：点击进入二级详情页 */
export function DramaProjectsPage() {
  const location = useLocation();
  const [page, setPage] = useAdminUrlState<number>("page", 1);
  const [q, setQ] = useAdminUrlState<string>("q", "");
  const [userId, setUserId] = useAdminUrlState<number | null>("user_id", null);
  const [summaryStatus, setSummaryStatus] = useAdminUrlState<string>("summary_status", "");
  const [assetsSeedStatus, setAssetsSeedStatus] = useAdminUrlState<string>("assets_seed_status", "");
  const { data, loading, error, run } = useAdminRequest<ListRes>();

  async function load(nextPage = page) {
  const params = new URLSearchParams({ page: String(nextPage), page_size: String(DEFAULT_PAGE_SIZE) });
  if (q.trim()) params.set("q", q.trim());
  if (userId) params.set("user_id", String(userId));
  if (summaryStatus.trim()) params.set("summary_status", summaryStatus.trim());
  if (assetsSeedStatus.trim()) params.set("assets_seed_status", assetsSeedStatus.trim());
    await run(() => api<ListRes>(`/api/admin/drama-projects?${params}`));
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  return (
    <div className="admin-list-page">
      <PageHeader description="漫剧项目：集数、资产、生产状态与费用；点击详情进入二级页" />
      <AdminFilterBar>
        <Input placeholder="标题 / 描述" value={q} onChange={(e) => setQ(e.target.value)} />
        <AdminUserSearchSelect value={userId} onChange={(id) => setUserId(id)} />
        <Input placeholder="摘要状态" value={summaryStatus} onChange={(e) => setSummaryStatus(e.target.value)} />
        <Input
          placeholder="资产抽取状态"
          value={assetsSeedStatus}
          onChange={(e) => setAssetsSeedStatus(e.target.value)}
        />
        <Button
          size="sm"
          variant="secondary"
          className="admin-filter-action"
          onClick={() => {
            if (page === 1) void load(1);
            else setPage(1);
          }}
        >
          筛选
        </Button>
      </AdminFilterBar>
      <AdminListState loading={loading} error={error} empty={!data?.items.length} onRetry={() => void load()}>
      <div className="admin-table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>标题</th>
              <th>用户</th>
              <th>集数</th>
              <th>资产</th>
              <th>费用</th>
              <th>摘要</th>
              <th>资产抽取</th>
              <th>更新时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td className="max-w-[200px] truncate">
                  <Link to={`/drama-projects/${row.id}`} state={{ from: `${location.pathname}${location.search}` }} className="admin-link font-medium">
                    {row.title}
                  </Link>
                </td>
                <td>
                  <AdminEntityLink kind="user" id={row.user_id} label={row.user_email ?? undefined} />
                </td>
                <td>{row.episode_count ?? 0}</td>
                <td>{row.asset_count ?? 0}</td>
                <td>¥{fenToYuan(row.charge_fen ?? 0)}</td>
                <td className="text-xs text-[var(--admin-muted)]">{row.summary_status || "—"}</td>
                <td className="text-xs text-[var(--admin-muted)]">{row.assets_seed_status || "—"}</td>
                <td className="text-xs text-[var(--admin-muted)]">
                  {row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}
                </td>
                <td>
                  <Button size="sm" variant="outline" asChild>
                    <Link to={`/drama-projects/${row.id}`} state={{ from: `${location.pathname}${location.search}` }}>详情</Link>
                  </Button>
                </td>
              </tr>
            ))}
            {(data?.items.length ?? 0) === 0 ? (
              <tr>
                <td colSpan={10} className="!text-center text-[var(--admin-muted)]">
                  暂无项目
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      </AdminListState>
      {!loading && !error && data?.meta ? (
        <PaginationBar
          page={data.meta.page}
          pageSize={data.meta.page_size}
          total={data.meta.total}
          onPageChange={setPage}
        />
      ) : null}
    </div>
  );
}
