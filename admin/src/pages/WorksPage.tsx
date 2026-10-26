import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, type AdminWork, type PageMeta } from "@/api/client";
import { AdminDetailMeta, AdminDetailSection } from "@/components/admin/AdminDetailLayout";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminModal } from "@/components/admin/AdminModal";
import { AdminSearchInput } from "@/components/admin/AdminSearchInput";
import { AdminUserSearchSelect } from "@/components/admin/AdminUserSearchSelect";
import { PaginationBar } from "@/components/PaginationBar";
import { DEFAULT_PAGE_SIZE } from "@/lib/pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { AdminField } from "@/components/admin/AdminField";
import { Textarea } from "@/components/ui/select";
import { AdminExportButton } from "@/components/admin/AdminExportButton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/ui/page";
import { useAdminDetailQuery } from "@/hooks/useAdminDetailQuery";
import { auditStatusLabel, visibilityLabel } from "@/lib/statusLabels";
import { hasPermission } from "@/lib/permissions";

type ListRes = { items: AdminWork[]; meta: PageMeta };
type WorkChange = { audit_status?: string; visibility?: string; audit_reason?: string };
type BulkResult = { results: { id: number; success: boolean; error?: string }[]; succeeded: number; failed: number };

function coverSrc(url: string | null | undefined): string {
  const trimmed = (url || "").trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return trimmed;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

// 作品审核：搜索、预览与只读详情
export function WorksPage() {
  const [auditStatus, setAuditStatus] = useAdminUrlState<string>("audit_status", "");
  const [visibility, setVisibility] = useAdminUrlState<string>("visibility", "");
  const [q, setQ] = useAdminUrlState<string>("q", "");
  const [userId, setUserId] = useAdminUrlState<number | null>("user_id", null);
  const [page, setPage] = useAdminUrlState<number>("page", 1);
  const { data, loading, error, run } = useAdminRequest<ListRes>();
  const [detail, setDetail] = useState<AdminWork | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRetry, setDetailRetry] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [action, setAction] = useState<{ ids: number[]; body: WorkChange } | null>(null);
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<number[]>([]);
  const actionLock = useRef(false);
  const workDetail = useAdminDetailQuery("work");
  const canReview = hasPermission("works:review");

  async function load(nextPage = page) {
  const params = new URLSearchParams({ page: String(nextPage), page_size: String(DEFAULT_PAGE_SIZE) });
  if (auditStatus) params.set("audit_status", auditStatus);
  if (visibility) params.set("visibility", visibility);
  if (q.trim()) params.set("q", q.trim());
  if (userId) params.set("user_id", String(userId));
    await run(() => api<ListRes>(`/api/admin/works?${params}`));
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  useEffect(() => {
    if (!workDetail.id) { setDetail(null); return; }
    let cancelled = false;
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    void api<AdminWork>(`/api/admin/works/${workDetail.id}`)
      .then((value) => { if (!cancelled) setDetail(value); })
      .catch((cause) => { if (!cancelled) setDetailError(cause instanceof Error ? cause.message : "加载作品失败"); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [workDetail.id, detailRetry]);

  useEffect(() => { setSelectedIds([]); }, [page, auditStatus, visibility, q, userId]);

  function reviewAction(ids: number[], body: WorkChange) {
    setAction({ ids, body });
    setReason("");
    setActionError(null);
  }

  async function submitAction() {
    if (!action || actionLock.current || !canReview) return;
    if (action.body.audit_status === "rejected" && !reason.trim()) {
      setActionError("请填写拒绝原因");
      return;
    }
    const body = { ...action.body, audit_reason: reason.trim() || undefined };
    actionLock.current = true;
    setPendingIds(action.ids);
    setActionError(null);
    try {
      let failedIds: number[] = [];
      if (action.ids.length === 1) {
        await api(`/api/admin/works/${action.ids[0]}`, { method: "PATCH", body: JSON.stringify(body) });
        toast.success("作品已更新");
      } else {
        const result = await api<BulkResult>("/api/admin/works/bulk", { method: "POST", body: JSON.stringify({ ids: action.ids, ...body }) });
        failedIds = result.results.filter((item) => !item.success).map((item) => item.id);
        if (result.failed) {
          setActionError(result.results.filter((item) => !item.success).map((item) => `#${item.id}：${item.error || "处理失败"}`).join("；"));
          setAction({ ids: failedIds, body: action.body });
          toast.warning(`已处理 ${result.succeeded} 项，${result.failed} 项失败`);
        } else toast.success(`已更新 ${result.succeeded} 个作品`);
      }
      await load();
      setSelectedIds(failedIds);
      if (!failedIds.length) setAction(null);
      if (workDetail.isOpen) setDetailRetry((value) => value + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "更新失败");
      toast.error(err instanceof Error ? err.message : "更新失败");
    } finally {
      actionLock.current = false;
      setPendingIds([]);
    }
  }

  function openWork(work: AdminWork) {
    workDetail.open(work.id);
  }

  const exportParams = new URLSearchParams();
  if (auditStatus) exportParams.set("audit_status", auditStatus);
  if (visibility) exportParams.set("visibility", visibility);
  if (q.trim()) exportParams.set("q", q.trim());
  if (userId) exportParams.set("user_id", String(userId));

  return (
    <div className="admin-list-page">
      <PageHeader description="调整可见性与审核状态" actions={<AdminExportButton path={`/api/admin/works/export?${exportParams}`} filename="作品审核.csv" />} />
      <AdminFilterBar>
        <AdminSearchInput
          value={q}
          onChange={setQ}
          placeholder="搜索标题"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              if (page === 1) void load(1);
              else setPage(1);
            }
          }}
        />
        <AdminUserSearchSelect value={userId} onChange={(id) => setUserId(id)} />
        <Select value={auditStatus} onChange={(e) => setAuditStatus(e.target.value)}>
          <option value="">全部审核</option>
          <option value="pending">待审核</option>
          <option value="passed">已通过</option>
          <option value="rejected">已拒绝</option>
        </Select>
        <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          <option value="">全部可见性</option>
          <option value="public">公开</option>
          <option value="private">私密</option>
          <option value="unlisted">不公开列出</option>
        </Select>
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
      {canReview && selectedIds.length ? <div className="admin-filter-bar" role="region" aria-label="批量操作">
        <span>已选 {selectedIds.length} 项（当前页）</span>
        <Button size="sm" disabled={!!pendingIds.length} onClick={() => reviewAction(selectedIds, { audit_status: "passed" })}>批量通过</Button>
        <Button size="sm" variant="outline" disabled={!!pendingIds.length} onClick={() => reviewAction(selectedIds, { audit_status: "rejected" })}>批量拒绝</Button>
        <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>取消选择</Button>
      </div> : null}
      <AdminListState loading={loading} error={error} empty={!data?.items.length} onRetry={() => void load()}>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              {canReview ? <TableHead><input type="checkbox" aria-label="选择当前页全部作品" checked={!!data?.items.length && selectedIds.length === data.items.length} onChange={(event) => setSelectedIds(event.target.checked ? (data?.items ?? []).map((item) => item.id) : [])} disabled={!!pendingIds.length} /></TableHead> : null}
              <TableHead>封面</TableHead>
              <TableHead>ID</TableHead>
              <TableHead>标题</TableHead>
              <TableHead>用户</TableHead>
              <TableHead>可见性</TableHead>
              <TableHead>审核</TableHead>
              <TableHead>发布时间</TableHead>
              <TableHead>操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items ?? []).map((w) => (
              <TableRow key={w.id}>
                {canReview ? <TableCell><input type="checkbox" aria-label={`选择作品 ${w.title}`} checked={selectedIds.includes(w.id)} disabled={!!pendingIds.length} onChange={(event) => setSelectedIds((ids) => event.target.checked ? [...ids, w.id] : ids.filter((id) => id !== w.id))} /></TableCell> : null}
                <TableCell>
                  {w.cover_url ? (
                    <button type="button" onClick={() => openWork(w)} className="block">
                      <img src={coverSrc(w.cover_url)} alt={w.title} className="admin-thumb" loading="lazy" />
                    </button>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell>{w.id}</TableCell>
                <TableCell className="max-w-[200px] truncate">
                  <button type="button" className="admin-link text-left" onClick={() => openWork(w)}>
                    {w.title}
                  </button>
                </TableCell>
                <TableCell>
                  <AdminEntityLink kind="user" id={w.user_id} label={w.user_email ?? undefined} />
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{visibilityLabel(w.visibility)}</Badge>
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      w.audit_status === "rejected"
                        ? "destructive"
                        : w.audit_status === "passed"
                          ? "success"
                          : "warning"
                    }
                  >
                    {auditStatusLabel(w.audit_status)}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(w.published_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    <Button size="sm" variant="outline" onClick={() => openWork(w)}>
                      详情
                    </Button>
                    {canReview ? <><Button size="sm" variant="outline" disabled={pendingIds.includes(w.id) || w.audit_status === "passed"} onClick={() => reviewAction([w.id], { audit_status: "passed" })}>
                      通过
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={pendingIds.includes(w.id) || w.audit_status === "rejected"}
                      onClick={() => reviewAction([w.id], { audit_status: "rejected" })}
                    >
                      拒绝
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={pendingIds.includes(w.id)}
                      onClick={() =>
                        reviewAction([w.id], {
                          visibility: w.visibility === "public" ? "private" : "public",
                        })
                      }
                    >
                      {w.visibility === "public" ? "设私密" : "设公开"}
                    </Button></> : null}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      </AdminListState>
      {!loading && !error && data && (
        <PaginationBar
          page={data.meta.page}
          pageSize={data.meta.page_size}
          total={data.meta.total}
          onPageChange={setPage}
        />
      )}

      <AdminModal
        open={workDetail.isOpen}
        presentation="drawer"
        onOpenChange={(open) => {
          if (!open) {
            setDetail(null);
            workDetail.close();
          }
        }}
        size="lg"
        title={detail?.title ?? "作品详情"}
        subtitle={detail ? `作品 #${detail.id}` : undefined}
      >
        {detailLoading ? <div className="admin-empty" role="status">加载作品详情…</div> : null}
        {detailError ? <div className="admin-empty" role="alert"><p>{detailError}</p><Button variant="outline" onClick={() => setDetailRetry((value) => value + 1)}>重试</Button></div> : null}
        {detail ? (
          <>
            {(detail.cover_url || detail.video_url) ? (
              <AdminDetailSection title="媒体预览">
                <div className="admin-detail-media">
                  {detail.cover_url ? (
                    <img src={coverSrc(detail.cover_url)} alt={detail.title} />
                  ) : null}
                  {detail.video_url ? (
                    <video src={detail.video_url} controls className="max-w-full" />
                  ) : null}
                </div>
              </AdminDetailSection>
            ) : null}
            <AdminDetailSection title="基本信息">
              <AdminDetailMeta
                items={[
                  {
                    label: "用户",
                    value: (
                      <AdminEntityLink
                        kind="user"
                        id={detail.user_id}
                        label={detail.user_email ?? undefined}
                      />
                    ),
                  },
                  {
                    label: "关联项目",
                    value: detail.project_id ? (
                      <AdminEntityLink kind="project" id={detail.project_id} />
                    ) : (
                      "—"
                    ),
                  },
                  { label: "可见性", value: visibilityLabel(detail.visibility) },
                  { label: "审核", value: auditStatusLabel(detail.audit_status) },
                  { label: "审核原因", value: detail.audit_reason || "—", full: true },
                  { label: "审核人", value: detail.audited_by ? `管理员 #${detail.audited_by}` : "—" },
                  { label: "审核时间", value: detail.audited_at ? new Date(detail.audited_at).toLocaleString() : "—" },
                  {
                    label: "发布时间",
                    value: new Date(detail.published_at).toLocaleString(),
                    full: true,
                  },
                ]}
              />
            </AdminDetailSection>
            {detail.video_url ? (
              <Button size="sm" variant="outline" asChild>
                <a href={detail.video_url} target="_blank" rel="noreferrer">
                  新窗口打开视频
                </a>
              </Button>
            ) : null}
          </>
        ) : null}
      </AdminModal>
      <AdminModal open={!!action} busy={!!pendingIds.length} onOpenChange={(open) => { if (!open && !pendingIds.length) setAction(null); }} size="md" title="确认作品操作" subtitle={action ? `将处理 ${action.ids.length} 个作品：${action.body.audit_status ? auditStatusLabel(action.body.audit_status) : visibilityLabel(action.body.visibility || "")}` : undefined} footer={<>
        <Button variant="outline" disabled={!!pendingIds.length} onClick={() => setAction(null)}>取消</Button>
        <Button disabled={!!pendingIds.length} onClick={() => void submitAction()}>{pendingIds.length ? "处理中…" : "确认提交"}</Button>
      </>}>
        <AdminField label={action?.body.audit_status === "rejected" ? "拒绝原因（必填）" : "操作备注"}>
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} placeholder="填写本次操作的原因" disabled={!!pendingIds.length} />
        </AdminField>
        {actionError ? <p role="alert" className="text-sm text-red-700">{actionError}</p> : null}
      </AdminModal>
    </div>
  );
}
