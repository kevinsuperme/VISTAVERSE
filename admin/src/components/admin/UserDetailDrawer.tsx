import { useEffect, useState } from "react";
import {
  api,
  type AdminLedger,
  type AdminOrder,
  type AdminUsageEvent,
  type AdminUserRow,
  type PageResult,
} from "@/api/client";
import { listAdminLedger, listAdminOrders, listAdminUsageEvents } from "@/api/finance";
import {
  AdminDetailMeta,
  AdminDetailSection,
  AdminDetailTableWrap,
} from "@/components/admin/AdminDetailLayout";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { AdminModal } from "@/components/admin/AdminModal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatAccountId } from "@/lib/admin-account";
import { fenToYuan } from "@/lib/utils";
import { ledgerKindLabel, orderStatusLabel } from "@/lib/statusLabels";
import { ADMIN_ROLE_LABELS, hasPermission } from "@/lib/permissions";

type ListRes<T> = PageResult<T>;

type UserDetailDrawerProps = {
  userId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialUser?: AdminUserRow | null;
};

/** 用户只读明细：基本信息 + 订单/流水/用量聚合 */
export function UserDetailDrawer({ userId, open, onOpenChange, initialUser }: UserDetailDrawerProps) {
  const [tab, setTab] = useState("info");
  const userRequest = useAdminRequest<AdminUserRow>();
  const orderRequest = useAdminRequest<ListRes<AdminOrder>>();
  const ledgerRequest = useAdminRequest<ListRes<AdminLedger>>();
  const usageRequest = useAdminRequest<ListRes<AdminUsageEvent>>();
  // Use the list row as an immediate snapshot, then replace it with the exact
  // detail response. This keeps the drawer responsive without weakening the
  // ID-specific refresh and stale-response guards below.
  const snapshot = initialUser?.id === userId ? initialUser : null;
  const user = userRequest.data?.id === userId ? userRequest.data : snapshot;
  const orders = orderRequest.data?.items ?? [];
  const ledger = ledgerRequest.data?.items ?? [];
  const usage = usageRequest.data?.items ?? [];
  const loading = userRequest.loading && !snapshot;
  const detailError = user ? null : userRequest.error;

  function loadUser() {
    if (userId) void userRequest.run(() => api<AdminUserRow>(`/api/admin/users/${userId}`));
  }

  function loadTab() {
    if (!userId) return;
    if (tab === "orders" && hasPermission("orders:read")) void orderRequest.run(() => listAdminOrders(1, { pageSize: 8, userId }));
    if (tab === "ledger" && hasPermission("finance:read")) void ledgerRequest.run(() => listAdminLedger(1, { pageSize: 8, userId }));
    if (tab === "usage" && hasPermission("finance:read")) void usageRequest.run(() => listAdminUsageEvents(1, { pageSize: 20, userId }));
  }

  useEffect(() => {
    userRequest.reset();
    orderRequest.reset();
    ledgerRequest.reset();
    usageRequest.reset();
    if (!open || !userId) return;
    setTab("info");
    loadUser();
    return () => { userRequest.cancel(); orderRequest.cancel(); ledgerRequest.cancel(); usageRequest.cancel(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, userId]);

  useEffect(() => {
    if (open && user?.id === userId) loadTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, userId, user?.id, tab]);

  return (
    <AdminModal
      open={open}
      presentation="drawer"
      onOpenChange={onOpenChange}
      size="xl"
      title="用户明细"
      subtitle={
        !loading && user
          ? `${user.email} · ID：${formatAccountId(user.id)}`
          : loading
            ? "加载中…"
            : "—"
      }
      bodyClassName="!pt-2"
    >
      <AdminListState loading={loading} error={detailError} empty={!user} onRetry={loadUser} emptyTitle="未找到该用户">
      {user ? (
        <Tabs value={tab} onValueChange={setTab} className="admin-detail-tabs">
          <TabsList>
            <TabsTrigger value="info">基本信息</TabsTrigger>
            {hasPermission("orders:read") ? <TabsTrigger value="orders">最近订单</TabsTrigger> : null}
            {hasPermission("finance:read") ? <><TabsTrigger value="ledger">钱包流水</TabsTrigger><TabsTrigger value="usage">用量摘要</TabsTrigger></> : null}
          </TabsList>
          <TabsContent value="info">
            <AdminDetailSection>
              <AdminDetailMeta
                items={[
                  { label: "昵称", value: user.nickname || "—" },
                  { label: "手机", value: user.phone || "—" },
                  { label: "角色", value: ADMIN_ROLE_LABELS[user.role] ?? user.role },
                  { label: "余额", value: `¥${fenToYuan(user.balance_fen)}` },
                  { label: "冻结", value: `¥${fenToYuan(user.frozen_fen)}` },
                  {
                    label: "注册时间",
                    value: user.created_at ? new Date(user.created_at).toLocaleString() : "—",
                    full: true,
                  },
                ]}
              />
            </AdminDetailSection>
          </TabsContent>
          <TabsContent value="orders">
            <AdminListState loading={orderRequest.loading} error={orderRequest.error} empty={!orders.length} onRetry={loadTab}>
            <AdminDetailTableWrap>
              <table>
                <thead>
                  <tr>
                    <th>单号</th>
                    <th>金额</th>
                    <th>状态</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="!text-center text-[var(--admin-muted)]">
                        暂无订单
                      </td>
                    </tr>
                  ) : (
                    orders.map((o) => (
                      <tr key={o.id}>
                        <td className="font-mono text-xs">{o.out_trade_no}</td>
                        <td>¥{fenToYuan(o.amount_fen)}</td>
                        <td>{orderStatusLabel(o.status)}</td>
                        <td className="text-xs">{new Date(o.created_at).toLocaleString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </AdminDetailTableWrap>
            </AdminListState>
          </TabsContent>
          <TabsContent value="ledger">
            <AdminListState loading={ledgerRequest.loading} error={ledgerRequest.error} empty={!ledger.length} onRetry={loadTab}>
            <AdminDetailTableWrap>
              <table>
                <thead>
                  <tr>
                    <th>类型</th>
                    <th>变动</th>
                    <th>余额后</th>
                    <th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="!text-center text-[var(--admin-muted)]">
                        暂无流水
                      </td>
                    </tr>
                  ) : (
                    ledger.map((row) => (
                      <tr key={row.id}>
                        <td>{ledgerKindLabel(row.kind)}</td>
                        <td>¥{fenToYuan(row.delta_fen)}</td>
                        <td>¥{fenToYuan(row.balance_after)}</td>
                        <td className="max-w-[200px] truncate text-xs">{row.note || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </AdminDetailTableWrap>
            </AdminListState>
          </TabsContent>
          <TabsContent value="usage">
            <AdminListState loading={usageRequest.loading} error={usageRequest.error} empty={!usage.length} onRetry={loadTab}>
            <AdminDetailTableWrap>
              <table>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>能力</th>
                    <th>扣费</th>
                    <th>成本</th>
                    <th>任务</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="!text-center text-[var(--admin-muted)]">
                        暂无用量
                      </td>
                    </tr>
                  ) : (
                    usage.map((row) => (
                      <tr key={row.id}>
                        <td className="text-xs">
                          {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                        </td>
                        <td>{row.capability || "—"}</td>
                        <td>¥{fenToYuan(row.charge_fen ?? 0)}</td>
                        <td>¥{fenToYuan(row.cost_fen ?? 0)}</td>
                        <td>
                          {row.task_run_id ? (
                            <AdminEntityLink kind="task" id={row.task_run_id} />
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </AdminDetailTableWrap>
            </AdminListState>
          </TabsContent>
        </Tabs>
      ) : null}
      </AdminListState>
    </AdminModal>
  );
}
