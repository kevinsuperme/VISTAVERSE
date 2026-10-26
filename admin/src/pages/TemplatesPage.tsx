import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { LayoutGrid, Plus } from "lucide-react";
import { toast } from "sonner";
import { api, type AdminTemplate, type PageMeta } from "@/api/client";
import { AdminChipFilter } from "@/components/admin/AdminChipFilter";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminSearchInput } from "@/components/admin/AdminSearchInput";
import { AdminSelect } from "@/components/admin/AdminSelect";
import { AdminListState } from "@/components/admin/AdminListState";
import { AdminModal } from "@/components/admin/AdminModal";
import { AdminExportButton } from "@/components/admin/AdminExportButton";
import { TemplateCard } from "@/components/templates/TemplateCard";
import { TemplateEditorDialog, type TemplateFormState } from "@/components/templates/TemplateEditorDialog";
import { PaginationBar } from "@/components/PaginationBar";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { TEMPLATE_PAGE_SIZE } from "@/lib/pagination";
import { hasPermission } from "@/lib/permissions";
import { validateTemplate } from "@/lib/templateValidation";
import { updateAdminQuery } from "@/lib/adminQueryState";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page";

type ListRes = { items: AdminTemplate[]; meta: PageMeta };
type MetaRes = { categories: string[]; category_counts: Record<string, number>; total: number };
type BulkResult = { results: { id: string; success: boolean; error?: string }[]; succeeded: number; failed: number };
const STATUS_OPTIONS = [{ value: "", label: "全部状态" }, { value: "active", label: "已上架" }, { value: "inactive", label: "已下架" }, { value: "premium", label: "Premium" }, { value: "standard", label: "非 Premium" }];
const emptyForm = (): TemplateFormState => ({ id: "", name: "", description: "", category: "", preview_cover: "", style_prefix: "", character_prompt: "", extra_prompt: "", negative_prompt: "", default_ratio: "16:9", shot_duration_min: 3, shot_duration_max: 8, llm_system_addon: "", sort_order: 0, is_active: true, is_premium: false });
function toForm(item: AdminTemplate): TemplateFormState {
  const text = (key: string) => typeof item.seedream_config?.[key] === "string" ? String(item.seedream_config[key]) : "";
  return { ...emptyForm(), ...item, category: (item.category || []).join(","), character_prompt: text("character_prompt"), extra_prompt: text("extra_prompt") };
}

export function TemplatesPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const rawPage = Number(params.get("page") || 1);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const q = params.get("q") || "";
  const statusFilter = STATUS_OPTIONS.some((item) => item.value === params.get("status")) ? params.get("status") || "" : "";
  const categoryFilter = params.get("category") || "";
  const detailId = params.get("template");
  const [searchText, setSearchText] = useState(q);
  const { data, loading, error, run } = useAdminRequest<ListRes>();
  const [meta, setMeta] = useState<MetaRes | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AdminTemplate | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRetry, setDetailRetry] = useState(0);
  const [form, setForm] = useState<TemplateFormState>(emptyForm());
  const [baseline, setBaseline] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [pendingIds, setPendingIds] = useState<string[]>([]);
  const [bulkTarget, setBulkTarget] = useState<boolean | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);
  const [discard, setDiscard] = useState(false);
  const locked = useRef(false);
  const canWrite = hasPermission("templates:write");
  const updateQuery = useCallback((update: (next: URLSearchParams) => void, replace = false) => {
    updateAdminQuery(location, location.search, update, setParams, replace);
  }, [location, setParams]);
  const dirty = JSON.stringify(form) !== baseline;
  const filterQuery = useMemo(() => {
    const next = new URLSearchParams();
    if (q.trim()) next.set("q", q.trim());
    if (categoryFilter) next.set("category", categoryFilter);
    if (statusFilter === "active" || statusFilter === "inactive") next.set("is_active", String(statusFilter === "active"));
    if (statusFilter === "premium" || statusFilter === "standard") next.set("is_premium", String(statusFilter === "premium"));
    return next.toString();
  }, [q, statusFilter, categoryFilter]);
  const load = useCallback(async () => {
    const query = new URLSearchParams(filterQuery);
    query.set("page", String(page)); query.set("page_size", String(TEMPLATE_PAGE_SIZE));
    await run(() => api<ListRes>(`/api/admin/templates?${query}`));
  }, [page, filterQuery, run]);
  const loadMeta = useCallback(async () => {
    try { setMeta(await api<MetaRes>("/api/admin/templates/meta")); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : "加载分类统计失败"); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadMeta(); }, [loadMeta]);
  useEffect(() => { setSearchText(q); }, [q]);
  useEffect(() => { setSelectedIds([]); setBulkResult(null); }, [page, filterQuery]);
  useEffect(() => {
    if (!detailId) { setEditing(null); return; }
    let cancelled = false;
    setCreating(false); setEditing(null); setDetailError(null);
    void api<AdminTemplate>(`/api/admin/templates/${encodeURIComponent(detailId)}`)
      .then((fresh) => { if (!cancelled) { const next = toForm(fresh); setEditing(fresh); setForm(next); setBaseline(JSON.stringify(next)); } })
      .catch((cause) => { if (!cancelled) setDetailError(cause instanceof Error ? cause.message : "加载模板详情失败"); });
    return () => { cancelled = true; };
  }, [detailId, detailRetry]);
  useEffect(() => {
    if (!data || data.meta.page !== page) return;
    const last = Math.max(1, Math.ceil(data.meta.total / TEMPLATE_PAGE_SIZE));
    if (page > last) updateQuery((next) => next.set("page", String(last)), true);
  }, [data, page, updateQuery]);

  function updateFilters(patch: Record<string, string>) {
    updateQuery((next) => { for (const [key, value] of Object.entries(patch)) { if (value) next.set(key, value); else next.delete(key); } next.set("page", "1"); });
  }
  function closeEditor(force = false) {
    if (saving) return;
    if (!force && canWrite && dirty) { setDiscard(true); return; }
    setCreating(false); setDiscard(false);
    updateQuery((next) => next.delete("template"), true);
  }
  function openCreate() {
    if (!canWrite) return;
    const next = emptyForm(); setForm(next); setBaseline(JSON.stringify(next)); setEditing(null); setCreating(true);
  }
  async function save() {
    if (!canWrite || locked.current) return;
    const validation = validateTemplate(form);
    if (validation) { toast.error(validation); return; }
    locked.current = true; setSaving(true);
    try {
      const category = [...new Set(form.category.split(/[,，]/).map((value) => value.trim()).filter(Boolean))];
      const body = { name: form.name.trim(), description: form.description, category, preview_cover: form.preview_cover.trim(), style_prefix: form.style_prefix, negative_prompt: form.negative_prompt, default_ratio: form.default_ratio, shot_duration_min: form.shot_duration_min, shot_duration_max: form.shot_duration_max, llm_system_addon: form.llm_system_addon, sort_order: form.sort_order, is_active: form.is_active, is_premium: form.is_premium, seedream_config: { ...(editing?.seedream_config || {}), character_prompt: form.character_prompt, extra_prompt: form.extra_prompt } };
      if (editing) await api(`/api/admin/templates/${encodeURIComponent(editing.id)}`, { method: "PATCH", body: JSON.stringify(body) });
      else await api("/api/admin/templates", { method: "POST", body: JSON.stringify({ ...body, id: form.id.trim(), seedance_config: {}, audio_config: {}, subtitle_config: {} }) });
      toast.success("模板已保存"); setCreating(false);
      updateQuery((next) => next.delete("template"), true);
      await Promise.all([load(), loadMeta()]);
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "保存失败，修改已保留"); }
    finally { locked.current = false; setSaving(false); }
  }
  async function quickPatch(id: string, body: Partial<AdminTemplate>) {
    if (!canWrite || locked.current) return;
    locked.current = true; setPendingIds([id]);
    try { await api(`/api/admin/templates/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }); toast.success("模板已更新"); await load(); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : "更新失败"); }
    finally { locked.current = false; setPendingIds([]); }
  }
  async function confirmDelete() {
    if (!canWrite || !deleteTarget || locked.current) return;
    locked.current = true; setPendingIds([deleteTarget]);
    try { await api(`/api/admin/templates/${encodeURIComponent(deleteTarget)}`, { method: "DELETE" }); toast.success("模板已删除"); setDeleteTarget(null); setSelectedIds((prev) => prev.filter((id) => id !== deleteTarget)); await Promise.all([load(), loadMeta()]); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : "删除失败"); }
    finally { locked.current = false; setPendingIds([]); }
  }
  async function applyBulk() {
    if (!canWrite || bulkTarget === null || !selectedIds.length || locked.current) return;
    locked.current = true; setPendingIds(selectedIds); setBulkResult(null);
    try {
      const result = await api<BulkResult>("/api/admin/templates/bulk", { method: "POST", body: JSON.stringify({ ids: selectedIds, is_active: bulkTarget }) });
      setBulkResult(result); setSelectedIds(result.results.filter((item) => !item.success).map((item) => item.id)); setBulkTarget(null);
      if (result.failed) toast.error(`成功 ${result.succeeded} 项，失败 ${result.failed} 项`); else toast.success(`已更新 ${result.succeeded} 个模板`);
      await load();
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "批量更新失败，选择已保留"); }
    finally { locked.current = false; setPendingIds([]); }
  }
  const categoryOptions = [{ value: "", label: "全部分类", count: meta?.total }, ...(meta?.categories || []).map((category) => ({ value: category, label: category, count: meta?.category_counts[category] ?? 0 }))];
  const items = data?.items || [];
  return <div className="admin-list-page">
    <PageHeader description="风格 / 角色 / 提示词以本页为准；已创建项目需在分镜页恢复模板后才会跟随。" actions={<div className="flex flex-wrap gap-2"><AdminExportButton path={`/api/admin/templates/export?${filterQuery}`} filename="templates.csv" />{canWrite ? <Button onClick={openCreate}><Plus className="h-4 w-4" />新建模板</Button> : null}</div>} />
    <AdminFilterBar trailing={<><LayoutGrid className="h-4 w-4" />{items.length} / {data?.meta.total ?? 0} 项</>}>
      <AdminSearchInput placeholder="搜索名称 / ID / 描述" value={searchText} onChange={setSearchText} onKeyDown={(event) => { if (event.key === "Enter") updateFilters({ q: searchText }); }} />
      <AdminSelect value={statusFilter} options={STATUS_OPTIONS} onChange={(value) => updateFilters({ status: value })} />
      <AdminChipFilter label="分类" value={categoryFilter} options={categoryOptions} onChange={(value) => updateFilters({ category: value })} />
      <Button variant="secondary" size="sm" onClick={() => updateFilters({ q: searchText })}>筛选</Button>
    </AdminFilterBar>
    {canWrite && items.length > 0 && !loading && !error ? <div className="flex flex-wrap items-center gap-3 admin-panel p-3">
      <label className="flex items-center gap-2"><input type="checkbox" checked={items.every((item) => selectedIds.includes(item.id))} disabled={pendingIds.length > 0} onChange={(event) => setSelectedIds(event.target.checked ? items.map((item) => item.id) : [])} />全选当前页</label>
      <span>已选 {selectedIds.length} 项</span>
      <Button size="sm" disabled={!selectedIds.length || pendingIds.length > 0} onClick={() => setBulkTarget(true)}>批量上架</Button>
      <Button size="sm" variant="outline" disabled={!selectedIds.length || pendingIds.length > 0} onClick={() => setBulkTarget(false)}>批量下架</Button>
    </div> : null}
    {bulkResult?.failed ? <div role="alert" className="admin-panel p-3 text-sm"><p>成功 {bulkResult.succeeded} 项，失败 {bulkResult.failed} 项；失败项已保留选择。</p><ul>{bulkResult.results.filter((item) => !item.success).map((item) => <li key={item.id}>{item.id}：{item.error || "更新失败"}</li>)}</ul></div> : null}
    <AdminListState loading={loading} error={error} empty={!items.length} emptyTitle="暂无匹配的模板" onRetry={() => void load()}>
      <div className="template-grid">{items.map((item) => <div key={item.id} className="min-w-0">
        {canWrite ? <label className="flex items-center gap-2 px-2 py-2 text-sm"><input type="checkbox" aria-label={`选择模板 ${item.name}`} checked={selectedIds.includes(item.id)} disabled={pendingIds.length > 0} onChange={(event) => setSelectedIds((prev) => event.target.checked ? [...prev, item.id] : prev.filter((id) => id !== item.id))} />选择</label> : null}
       <TemplateCard template={item} canWrite={canWrite} busy={pendingIds.length > 0} onEdit={(template) => updateQuery((next) => next.set("template", template.id))} onDelete={setDeleteTarget} onToggleActive={(id, value) => void quickPatch(id, { is_active: value })} onTogglePremium={(id, value) => void quickPatch(id, { is_premium: value })} />
      </div>)}</div>
    </AdminListState>
    {data && data.meta.total > TEMPLATE_PAGE_SIZE ? <PaginationBar page={page} pageSize={TEMPLATE_PAGE_SIZE} total={data.meta.total} onPageChange={(nextPage) => updateQuery((next) => next.set("page", String(nextPage)))} /> : null}
    <AdminModal open={Boolean(detailId && (!editing || editing.id !== detailId))} onOpenChange={(next) => { if (!next) closeEditor(true); }} title="模板详情" size="lg"><AdminListState loading={!detailError} error={detailError} empty={false} onRetry={() => { setDetailError(null); setDetailRetry((value) => value + 1); }}>{null}</AdminListState></AdminModal>
    <TemplateEditorDialog open={creating || Boolean(detailId && editing?.id === detailId)} saving={saving} editing={editing} form={form} readOnly={!canWrite} categorySuggestions={meta?.categories || []} onOpenChange={(next) => { if (!next) closeEditor(); }} onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))} onSave={() => void save()} />
    <AdminConfirmDialog open={Boolean(deleteTarget)} title="删除模板" description={`确认删除模板「${deleteTarget || ""}」？已被项目引用的模板无法删除。`} confirmLabel="删除" loading={pendingIds.length > 0} destructive onOpenChange={(next) => { if (!next) setDeleteTarget(null); }} onConfirm={() => void confirmDelete()} />
    <AdminConfirmDialog open={bulkTarget !== null} title={bulkTarget ? "批量上架模板" : "批量下架模板"} description={`将更新已选的 ${selectedIds.length} 个模板。`} loading={pendingIds.length > 0} onOpenChange={(next) => { if (!next) setBulkTarget(null); }} onConfirm={() => void applyBulk()} />
    <AdminConfirmDialog open={discard} title="放弃未保存的模板修改？" description="关闭后会丢弃本次修改。" confirmLabel="放弃修改" onOpenChange={setDiscard} onConfirm={() => closeEditor(true)} />
  </div>;
}
