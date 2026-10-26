import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, type AdminStats, type AdminUserRow, type PageMeta } from "@/api/client";
import { AdminField } from "@/components/admin/AdminField";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminListStats } from "@/components/admin/AdminListStats";
import { AdminModal } from "@/components/admin/AdminModal";
import { AdminSearchInput } from "@/components/admin/AdminSearchInput";
import { UserDetailDrawer } from "@/components/admin/UserDetailDrawer";
import { PaginationBar } from "@/components/PaginationBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, PageHeader } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAdminDetailQuery } from "@/hooks/useAdminDetailQuery";
import { formatAccountId } from "@/lib/admin-account";
import { DEFAULT_PAGE_SIZE } from "@/lib/pagination";
import { fenToYuan } from "@/lib/utils";
import { ADMIN_ROLE_LABELS, hasPermission } from "@/lib/permissions";
import { getCachedUser } from "@/lib/auth";
import { buildBalanceAdjustment, createAdjustmentRequestId } from "@/lib/balanceAdjustment";

type ListRes = { items: AdminUserRow[]; meta: PageMeta };

// 用户管理：搜索、筛选、只读明细与编辑
export function UsersPage() {
  const [q, setQ] = useAdminUrlState<string>("q", "");
  const [roleFilter, setRoleFilter] = useAdminUrlState<string>("role", "");
  const [page, setPage] = useAdminUrlState<number>("page", 1);
  const [pageSize, setPageSize] = useAdminUrlState<number>("page_size", DEFAULT_PAGE_SIZE);
  const { data, loading, error, run } = useAdminRequest<ListRes>();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [editing, setEditing] = useState<AdminUserRow | null>(null);
  const [editMode, setEditMode] = useState<"role" | "balance">("role");
  const [confirming, setConfirming] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [detailUser, setDetailUser] = useState<AdminUserRow | null>(null);
  const [form, setForm] = useState({
    role: "user",
    /** increase=增加 / decrease=减少 */
    balance_dir: "increase" as "increase" | "decrease",
    /** 调账金额（元），空表示不改余额 */
    balance_amount_yuan: "",
    balance_note: "",
  });
  const [saving, setSaving] = useState(false);
  const saveLock = useRef(false);
  const balanceRequestId = useRef("");
  const userDetail = useAdminDetailQuery("user");

  async function load(nextPage = page, nextQ = q, nextSize = pageSize) {
    const params = new URLSearchParams({ page: String(nextPage), page_size: String(nextSize) });
    if (nextQ.trim()) params.set("q", nextQ.trim());
    if (roleFilter) params.set("role", roleFilter);
    await run(() => api<ListRes>(`/api/admin/users?${params}`));
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  useEffect(() => {
    void api<AdminStats>("/api/admin/stats?days=7")
      .then(setStats)
      .catch((err) => {
        setStats(null);
        toast.error(err instanceof Error ? err.message : "统计加载失败");
      });
  }, []);

  useEffect(() => {
    if (!userDetail.id || !data?.items) return;
    const hit = data.items.find((u) => u.id === userDetail.id);
    if (hit) setDetailUser(hit);
  }, [userDetail.id, data?.items]);

  function openEdit(user: AdminUserRow, mode: "role" | "balance") {
    balanceRequestId.current = createAdjustmentRequestId();
    setEditing(user);
    setEditMode(mode);
    setFormError(null);
    setConfirming(false);
    setForm({
      role: user.role || "user",
      balance_dir: "increase",
      balance_amount_yuan: "",
      balance_note: "",
    });
  }

  function updateBalanceForm(patch: Partial<typeof form>) {
    balanceRequestId.current = createAdjustmentRequestId();
    setForm((previous) => ({ ...previous, ...patch }));
  }

  async function saveEdit() {
    if (!editing || saveLock.current || !hasPermission(editMode === "role" ? "users:role" : "balance:write")) return;
    saveLock.current = true;
    setSaving(true);
    try {
      const payload = editMode === "role" ? { role: form.role } : buildBalanceAdjustment(
        form.balance_amount_yuan, form.balance_dir, editing.balance_fen, form.balance_note, balanceRequestId.current,
      );

      await api(`/api/admin/users/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      toast.success(editMode === "balance" ? "已调账并保存" : "已保存");
      setConfirming(false);
      setEditing(null);
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      if (editMode === "balance" && /409|余额已变化|expected_balance|并发/.test(message)) {
        setEditing(null);
        setConfirming(false);
        await load();
        setFormError("余额已被其他操作更新，请重新打开用户详情并核对最新余额后再调账");
      }
      setFormError(editMode === "balance" && /409|余额已变化|expected_balance|并发/.test(message)
        ? "余额已被其他操作更新，请重新打开用户详情并核对最新余额后再调账" : message);
      setConfirming(false);
      toast.error(message);
    } finally {
      saveLock.current = false;
      setSaving(false);
    }
  }

  function applyFilters() {
    if (page === 1) void load(1, q, pageSize);
    else setPage(1);
  }

  const amountFen = Math.round(Number(form.balance_amount_yuan || 0) * 100);
  const balanceAfter = editing ? editing.balance_fen + (form.balance_dir === "decrease" ? -amountFen : amountFen) : 0;

  function reviewChange() {
    setFormError(null);
    if (editMode === "balance") {
      try { buildBalanceAdjustment(form.balance_amount_yuan, form.balance_dir, editing?.balance_fen ?? 0, form.balance_note, balanceRequestId.current); }
      catch (cause) { setFormError(cause instanceof Error ? cause.message : "请检查调账信息"); return; }
    } else if (form.role === editing?.role) { setFormError("角色未发生变化"); return; }
    else if (editing?.id === getCachedUser()?.id && form.role !== "admin") { setFormError("不能降低自己的管理员权限"); return; }
    setConfirming(true);
  }

  return (
    <div className="admin-list-page">
      <PageHeader description="搜索用户，调整角色与余额" />

      <AdminFilterBar>
        <AdminSearchInput
          value={q}
          onChange={setQ}
          placeholder="搜索邮箱 / 昵称 / 账号 ID"
          onKeyDown={(e) => {
            if (e.key === "Enter") applyFilters();
          }}
        />
        <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="">全部角色</option>
          {Object.entries(ADMIN_ROLE_LABELS).map(([role, label]) => <option key={role} value={role}>{label}</option>)}
        </Select>
        <Button size="sm" className="admin-filter-action" onClick={applyFilters} disabled={loading}>
          {loading ? "加载中…" : "搜索"}
        </Button>
      </AdminFilterBar>

      <AdminListStats
        items={[
          { label: "总用户数", value: stats?.user_count ?? (loading ? "…" : "—") },
          {
            label: "本月调用",
            value: stats != null ? (stats.usage_calls_month ?? 0) : loading ? "…" : "—",
            hint: stats ? `今日 ${stats.usage_calls_today ?? 0} 次` : undefined,
          },
          {
            label: "累计调用",
            value: stats != null ? (stats.usage_calls_total ?? 0) : loading ? "…" : "—",
          },
        ]}
      />

      <div className="space-y-3">
        <AdminListState loading={loading} error={error} empty={!data?.items.length} onRetry={() => void load()} emptyTitle="暂无匹配用户">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>账号 ID</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>昵称</TableHead>
              <TableHead>手机</TableHead>
              <TableHead>余额</TableHead>
              <TableHead>冻结</TableHead>
              <TableHead>角色</TableHead>
              <TableHead>注册时间</TableHead>
              <TableHead className="w-[140px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items ?? []).map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-mono text-xs text-[#909399]">{formatAccountId(u.id)}</TableCell>
                <TableCell className="font-medium">{u.email}</TableCell>
                <TableCell>{u.nickname || "—"}</TableCell>
                <TableCell className="text-xs">{u.phone || "—"}</TableCell>
                <TableCell className="tabular-nums">¥{fenToYuan(u.balance_fen)}</TableCell>
                <TableCell className="tabular-nums">¥{fenToYuan(u.frozen_fen)}</TableCell>
                <TableCell>
                  <Badge variant={u.role === "admin" ? "success" : "secondary"}>{ADMIN_ROLE_LABELS[u.role] ?? u.role}</Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {u.created_at ? new Date(u.created_at).toLocaleString() : "—"}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setDetailUser(u);
                        userDetail.open(u.id);
                      }}
                    >
                      查看
                    </Button>
                    {hasPermission("users:role") ? <Button size="sm" variant="ghost" onClick={() => openEdit(u, "role")}>
                      角色
                    </Button> : null}
                    {hasPermission("balance:write") ? <Button size="sm" variant="ghost" onClick={() => openEdit(u, "balance")}>
                      调账
                    </Button> : null}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!loading && (data?.items.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="p-0">
                  <EmptyState title="暂无用户" description="试试换个关键词搜索" />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </AdminListState>

        {!loading && !error && data && (
          <PaginationBar
            page={data.meta.page}
            pageSize={pageSize}
            total={data.meta.total}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        )}
      </div>

      <UserDetailDrawer
        userId={userDetail.id}
        open={userDetail.isOpen}
        onOpenChange={(open) => {
          if (!open) userDetail.close();
        }}
        initialUser={detailUser}
      />

      <AdminModal
        open={!!editing}
        busy={saving}
        onOpenChange={(open) => { if (!open && !saving) setEditing(null); }}
        size="md"
        title={editMode === "role" ? "调整用户角色" : "手动调账"}
        subtitle={editing?.email}
        footer={
          <Button className="w-full sm:w-auto" disabled={saving} onClick={reviewChange}>
            {saving ? "保存中…" : "核对并继续"}
          </Button>
        }
      >
        {formError ? <p role="alert" className="text-sm text-red-700">{formError}</p> : null}
        <div className="admin-form-grid admin-form-grid--2">
          {editMode === "role" ? <>
          <AdminField label="角色">
            <Select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
              {Object.entries(ADMIN_ROLE_LABELS).map(([role, label]) => <option key={role} value={role} disabled={editing?.id === getCachedUser()?.id && role !== "admin"}>{label}</option>)}
            </Select>
          </AdminField>
          </> : <>
          <AdminField label="当前余额" hint="只读">
            <Input value={editing ? `¥${fenToYuan(editing.balance_fen)}` : "—"} disabled readOnly />
          </AdminField>
          <AdminField label="调账方向">
            <Select
              value={form.balance_dir}
              onChange={(e) =>
                updateBalanceForm({
                  balance_dir: e.target.value === "decrease" ? "decrease" : "increase",
                })
              }
            >
              <option value="increase">增加</option>
              <option value="decrease">减少</option>
            </Select>
          </AdminField>
          <AdminField
            label="调账金额（元）"
            hint={
              form.balance_amount_yuan.trim()
                ? form.balance_dir === "increase"
                  ? "保存后余额将增加该金额"
                  : "保存后余额将减少该金额"
                : "请输入本次需要调整的金额"
            }
          >
            <Input
              type="number"
              min="0"
              max="21474836.47"
              step="0.01"
              inputMode="decimal"
              value={form.balance_amount_yuan}
              onChange={(e) => updateBalanceForm({ balance_amount_yuan: e.target.value })}
              placeholder="例如 100"
            />
          </AdminField>
          <AdminField label="调账原因（必填）" hint="随操作人和金额写入调账流水">
            <Input
              value={form.balance_note}
              maxLength={255}
              onChange={(e) => updateBalanceForm({ balance_note: e.target.value })}
              placeholder="管理员备注"
            />
          </AdminField>
          <p className="admin-form-grid--full text-sm" aria-live="polite">预计余额：¥{Number.isFinite(balanceAfter) ? fenToYuan(balanceAfter) : "—"}</p>
          </>}
        </div>
      </AdminModal>
      <AdminConfirmDialog
        open={confirming}
        onOpenChange={(open) => { if (!saving) setConfirming(open); }}
        title={editMode === "role" ? "确认角色变更" : "确认手动调账"}
        description={editMode === "role"
          ? `将 ${editing?.email ?? ""} 的角色由 ${ADMIN_ROLE_LABELS[editing?.role ?? ""] ?? editing?.role ?? ""} 改为 ${ADMIN_ROLE_LABELS[form.role] ?? form.role}。该操作将改变后台访问权限。`
          : `${editing?.email ?? ""}：余额 ¥${fenToYuan(editing?.balance_fen ?? 0)} → ¥${fenToYuan(balanceAfter)}，原因：${form.balance_note.trim()}`}
        confirmLabel="确认提交"
        loading={saving}
        onConfirm={() => void saveEdit()}
      />
    </div>
  );
}
