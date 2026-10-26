import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import { useEffect, useState } from "react";
import { api, type AdminProject, type PageMeta } from "@/api/client";
import {
  AdminDetailMeta,
  AdminDetailNote,
  AdminDetailSection,
  AdminDetailStatGrid,
  AdminDetailTableWrap,
} from "@/components/admin/AdminDetailLayout";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminModal } from "@/components/admin/AdminModal";
import { AdminUserSearchSelect } from "@/components/admin/AdminUserSearchSelect";
import { PaginationBar } from "@/components/PaginationBar";
import { DEFAULT_PAGE_SIZE } from "@/lib/pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/ui/page";
import { useAdminDetailQuery } from "@/hooks/useAdminDetailQuery";
import { PROJECT_STATUS_OPTIONS, projectStatusLabel, taskStatusLabel, taskTypeLabel } from "@/lib/statusLabels";
import { fenToYuan } from "@/lib/utils";

type ListRes = { items: AdminProject[]; meta: PageMeta };

function statusBadgeVariant(status: string): "destructive" | "success" | "warning" | "info" | "secondary" {
  if (status === "FAILED" || status === "REJECTED") return "destructive";
  if (status === "DONE") return "success";
  if (status === "CANCELLED") return "secondary";
  if (status === "DRAFT") return "secondary";
  return "info";
}

function mediaSrc(url: string | null | undefined): string {
  const trimmed = (url || "").trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return trimmed;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

// 科普项目列表与详情（镜头 / 任务 / 费用 / 媒体预览）
export function ProjectsPage() {
  const [q, setQ] = useAdminUrlState<string>("q", "");
  const [status, setStatus] = useAdminUrlState<string>("status", "");
  const [userId, setUserId] = useAdminUrlState<number | null>("user_id", null);
  const [page, setPage] = useAdminUrlState<number>("page", 1);
  const { data, loading, error, run } = useAdminRequest<ListRes>();
  const [detail, setDetail] = useState<AdminProject | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRetry, setDetailRetry] = useState(0);
  const projectDetail = useAdminDetailQuery("open");

  async function load(nextPage = page) {
  const params = new URLSearchParams({ page: String(nextPage), page_size: String(DEFAULT_PAGE_SIZE) });
  if (status) params.set("status", status);
  if (q.trim()) params.set("q", q.trim());
  if (userId) params.set("user_id", String(userId));
    await run(() => api<ListRes>(`/api/admin/projects?${params}`));
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  function openDetail(id: number) {
    projectDetail.open(id);
  }

  useEffect(() => {
    if (!projectDetail.id) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    void api<AdminProject>(`/api/admin/projects/${projectDetail.id}`)
      .then((value) => { if (!cancelled) setDetail(value); })
      .catch((cause) => { if (!cancelled) setDetailError(cause instanceof Error ? cause.message : "加载详情失败"); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [projectDetail.id, detailRetry]);

  const usage = detail?.usage;

  return (
    <div className="admin-list-page">
      <PageHeader description="科普管线项目：状态、镜头、关联任务与费用" />
      <AdminFilterBar>
        <Select value={status} onChange={(e) => setStatus(e.target.value)}>
          {PROJECT_STATUS_OPTIONS.map((opt) => (
            <option key={opt.value || "all"} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <Input placeholder="标题 / 错误信息" value={q} onChange={(e) => setQ(e.target.value)} />
        <AdminUserSearchSelect value={userId} onChange={(id) => setUserId(id)} />
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
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>标题</TableHead>
              <TableHead>用户</TableHead>
              <TableHead>模板</TableHead>
              <TableHead>管线</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>进度</TableHead>
              <TableHead>镜头</TableHead>
              <TableHead>费用</TableHead>
              <TableHead>创建</TableHead>
              <TableHead>更新</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items ?? []).map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.id}</TableCell>
                <TableCell className="max-w-[180px] truncate">{p.title}</TableCell>
                <TableCell className="text-sm">
                  <AdminEntityLink kind="user" id={p.user_id} label={p.user_email ?? undefined} />
                </TableCell>
                <TableCell className="font-mono text-xs">{p.template_id}</TableCell>
                <TableCell className="text-xs">{p.pipeline_mode}</TableCell>
                <TableCell>
                  <Badge variant={statusBadgeVariant(p.status)}>{projectStatusLabel(p.status)}</Badge>
                </TableCell>
                <TableCell>{p.progress}%</TableCell>
                <TableCell>{p.shot_count}</TableCell>
                <TableCell>¥{fenToYuan(p.charge_fen ?? 0)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(p.created_at).toLocaleString()}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(p.updated_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" onClick={() => void openDetail(p.id)}>
                    详情
                  </Button>
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
        open={projectDetail.isOpen}
        presentation="drawer"
        onOpenChange={(open) => {
          if (!open) {
            setDetail(null);
            projectDetail.close();
          }
        }}
        size="full"
        title={detail ? `科普项目 #${detail.id} · ${detail.title}` : "科普项目详情"}
        subtitle={detail ? projectStatusLabel(detail.status) : detailLoading ? "加载中…" : undefined}
        bodyClassName="space-y-3"
      >
        {detailError ? <div className="admin-empty" role="alert"><p>{detailError}</p><Button variant="outline" onClick={() => setDetailRetry((value) => value + 1)}>重试</Button></div> : null}
        {detailLoading && !detail ? (
          <div className="py-10 text-center text-sm text-[var(--admin-muted)]">加载中…</div>
        ) : null}
        {detail ? (
          <>
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
                    label: "状态 / 进度",
                    value: `${projectStatusLabel(detail.status)} · ${detail.progress}% · 镜头 ${detail.shot_count}`,
                  },
                  { label: "模板", value: detail.template_id },
                  { label: "管线", value: detail.pipeline_mode },
                  { label: "来源", value: detail.source_type || "—" },
                  {
                    label: "分辨率 / 比例",
                    value: `${detail.resolution_mode || "—"} · ${detail.output_ratio || "—"}`,
                  },
                  { label: "配音", value: detail.voice_id || "—", full: true },
                ]}
              />
              <AdminDetailNote empty={!detail.error_msg} className="mt-3">
                {detail.error_msg || "无错误信息"}
              </AdminDetailNote>
            </AdminDetailSection>

            {(detail.cover_url || detail.final_video_url) ? (
              <AdminDetailSection title="媒体预览">
                <div className="admin-detail-media">
                  {detail.cover_url ? (
                    <img src={mediaSrc(detail.cover_url)} alt="封面" />
                  ) : null}
                  {detail.final_video_url ? (
                    <video src={mediaSrc(detail.final_video_url)} controls className="max-w-full" />
                  ) : null}
                </div>
              </AdminDetailSection>
            ) : null}

            <AdminDetailSection title="费用汇总">
              <AdminDetailStatGrid
                items={[
                  { label: "扣费", value: `¥${fenToYuan(usage?.charge_fen ?? detail.charge_fen ?? 0)}` },
                  { label: "成本", value: `¥${fenToYuan(usage?.cost_fen ?? 0)}` },
                  { label: "Tokens", value: usage?.tokens ?? 0 },
                  {
                    label: "图/视/LLM/TTS",
                    value: `${usage?.image_gens ?? 0}/${usage?.video_gens ?? 0}/${usage?.llm_calls ?? 0}/${usage?.tts_gens ?? 0}`,
                  },
                ]}
              />
            </AdminDetailSection>

            <AdminDetailSection title={`镜头（${(detail.shots ?? []).length}）`}>
              <AdminDetailTableWrap>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>状态</th>
                      <th>时长</th>
                      <th>图</th>
                      <th>视频</th>
                      <th>音频</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.shots ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={6} className="!text-center text-[var(--admin-muted)]">
                          暂无镜头
                        </td>
                      </tr>
                    ) : (
                      (detail.shots ?? []).map((s) => (
                        <tr key={s.id}>
                          <td>{s.shot_no}</td>
                          <td>{s.status}</td>
                          <td>{s.duration}s</td>
                          <td>{s.has_image ? "有" : "—"}</td>
                          <td>{s.has_video ? "有" : "—"}</td>
                          <td>{s.has_audio ? "有" : "—"}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </AdminDetailTableWrap>
            </AdminDetailSection>

            <AdminDetailSection title={`关联任务（最近 ${(detail.recent_tasks ?? []).length}）`}>
              <AdminDetailTableWrap className="max-h-[200px]">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>类型</th>
                      <th>状态</th>
                      <th>已扣 / 预估</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.recent_tasks ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={4} className="!text-center text-[var(--admin-muted)]">
                          暂无任务
                        </td>
                      </tr>
                    ) : (
                      (detail.recent_tasks ?? []).map((t) => (
                        <tr key={t.id}>
                          <td>
                            <AdminEntityLink kind="task" id={t.id} />
                          </td>
                          <td>{taskTypeLabel(t.task_type)}</td>
                          <td>{taskStatusLabel(t.status)}</td>
                          <td>
                            ¥{fenToYuan(t.billing_charged_fen)} / ¥{fenToYuan(t.billing_estimate_fen)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </AdminDetailTableWrap>
            </AdminDetailSection>

            {detail.source_text ? (
              <AdminDetailSection title="源文本">
                <AdminDetailNote>{detail.source_text}</AdminDetailNote>
              </AdminDetailSection>
            ) : null}
          </>
        ) : null}
      </AdminModal>
    </div>
  );
}
