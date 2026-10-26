import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import type { AdminLedger, AdminOrder, AdminUsageEventListRes, PageResult } from "@/api/client";
import { api } from "@/api/client";
import { AdminListState } from "@/components/admin/AdminListState";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { listAdminLedger, listAdminOrders, listAdminUsageEvents } from "@/api/finance";
import { AdminDateRangeFilter } from "@/components/admin/AdminDateRangeFilter";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminUserSearchSelect } from "@/components/admin/AdminUserSearchSelect";
import { LedgerDetailDialog, LedgerRefLink, OrderDetailDialog } from "@/components/finance/FinanceDetailDialogs";
import { PaginationBar } from "@/components/PaginationBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/ui/page";
import { useAdminDetailQuery } from "@/hooks/useAdminDetailQuery";
import { fenToYuan } from "@/lib/utils";
import { ledgerKindLabel, orderStatusLabel, payTypeLabel, taskDomainLabel } from "@/lib/statusLabels";
import { hasPermission } from "@/lib/permissions";

type OrderRes = PageResult<AdminOrder>;
type LedgerRes = PageResult<AdminLedger>;

const ORDER_TABS = new Set(["orders", "ledger", "usage"]);

// 将 URL 中的 Tab 限定为已有的财务列表，兼容无参数入口。
function tabFromSearch(raw: string | null): string {
  return raw && ORDER_TABS.has(raw) ? raw : "orders";
}

// 充值订单、钱包流水与用量明细
export function OrdersPage() {
  // 列表筛选与分页分别保留，切换 Tab 不清空其他列表状态。
  const [searchParams, setSearchParams] = useSearchParams();
  const canReadFinance = hasPermission("finance:read");
  const tab = canReadFinance ? tabFromSearch(searchParams.get("tab")) : "orders";
  const [orderStatus, setOrderStatus] = useAdminUrlState<string>("order_status", "");
  const [orderUserId, setOrderUserId] = useAdminUrlState<number | null>("order_user", null);
  const [ledgerKind, setLedgerKind] = useAdminUrlState<string>("ledger_kind", "");
  const [ledgerUserId, setLedgerUserId] = useAdminUrlState<number | null>("ledger_user", null);
  const [orderPage, setOrderPage] = useAdminUrlState<number>("order_page", 1);
  const [ledgerPage, setLedgerPage] = useAdminUrlState<number>("ledger_page", 1);
  const [usagePage, setUsagePage] = useAdminUrlState<number>("usage_page", 1);
  const [usageUserId, setUsageUserId] = useAdminUrlState<number | null>("usage_user", null);
  const [usageTaskId, setUsageTaskId] = useAdminUrlState<string>("task_id", "");
  const [usageDomain, setUsageDomain] = useAdminUrlState<string>("domain", "");
  const [usageBillingKey, setUsageBillingKey] = useAdminUrlState<string>("billing_key", "");
  const [usageCapability, setUsageCapability] = useAdminUrlState<string>("capability", "");
  const [usageModel, setUsageModel] = useAdminUrlState<string>("model", "");
  const [usageBasis, setUsageBasis] = useAdminUrlState<string>("basis", "");
  const [usageDateFrom, setUsageDateFrom] = useAdminUrlState<string>("from", "");
  const [usageDateTo, setUsageDateTo] = useAdminUrlState<string>("to", "");
  const orderRequest = useAdminRequest<OrderRes>();
  const ledgerRequest = useAdminRequest<LedgerRes>();
  const usageRequest = useAdminRequest<AdminUsageEventListRes>();
  const orders = orderRequest.data;
  const ledger = ledgerRequest.data;
  const usage = usageRequest.data;
  const [orderDetail, setOrderDetail] = useState<AdminOrder | null>(null);
  const [orderDetailLoading, setOrderDetailLoading] = useState(false);
  const [orderDetailError, setOrderDetailError] = useState<string | null>(null);
  const [orderDetailRetry, setOrderDetailRetry] = useState(0);
  const [ledgerDetail, setLedgerDetail] = useState<AdminLedger | null>(null);
  const orderQuery = useAdminDetailQuery("order");

  // 按当前筛选加载充值订单，分页仍由服务端完成。
  async function loadOrders(page = orderPage) {
    await orderRequest.run(() => listAdminOrders(page, { status: orderStatus, userId: orderUserId }));
  }

  // 加载钱包流水；与调账页、用户详情共享请求参数映射。
  async function loadLedger(page = ledgerPage) {
    if (!canReadFinance) return;
    await ledgerRequest.run(() => listAdminLedger(page, { kind: ledgerKind, userId: ledgerUserId }));
  }

  // 支持快捷筛选覆盖尚未提交到 React state 的用量条件。
  async function loadUsage(
    page = usagePage,
    overrides?: { billing_key?: string; capability?: string; model?: string },
  ) {
    if (!canReadFinance) return;
    await usageRequest.run(() => listAdminUsageEvents(page, {
        userId: usageUserId,
        taskRunId: usageTaskId.trim(),
        domain: usageDomain,
        billingKey: overrides?.billing_key ?? usageBillingKey.trim(),
        capability: overrides?.capability ?? usageCapability.trim(),
        model: overrides?.model ?? usageModel.trim(),
        billingBasis: usageBasis,
        dateFrom: usageDateFrom,
        dateTo: usageDateTo,
    }));
  }

  useEffect(() => {
    if (tab === "orders") void loadOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, orderPage]);

  useEffect(() => {
    if (tab === "ledger") void loadLedger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, ledgerPage]);

  useEffect(() => {
    if (tab === "usage") void loadUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, usagePage]);

  useEffect(() => {
    if (!orderQuery.id) { setOrderDetail(null); return; }
    let cancelled = false;
    setOrderDetail(null);
    setOrderDetailLoading(true);
    setOrderDetailError(null);
    void api<AdminOrder>(`/api/admin/orders/${orderQuery.id}`)
      .then((value) => { if (!cancelled) setOrderDetail(value); })
      .catch((cause) => { if (!cancelled) setOrderDetailError(cause instanceof Error ? cause.message : "加载订单详情失败"); })
      .finally(() => { if (!cancelled) setOrderDetailLoading(false); });
    return () => { cancelled = true; };
  }, [orderQuery.id, orderDetailRetry]);

  const tradeNo = searchParams.get("trade");
  useEffect(() => {
    if (!tradeNo) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await listAdminOrders(1, { pageSize: 1, outTradeNo: tradeNo });
        const hit = res.items[0];
        if (hit && !cancelled) {
          setOrderDetail(hit);
          orderQuery.open(hit.id);
        } else if (!cancelled) toast.error("未找到该商户订单");
      } catch (cause) {
        if (!cancelled) toast.error(cause instanceof Error ? cause.message : "订单定位失败");
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeNo]);

  // 将激活列表同步到 URL，保证刷新和跨页深链保持一致。
  function onTabChange(next: string) {
    if (next !== "orders" && !canReadFinance) return;
    const params = new URLSearchParams(searchParams);
    if (next === "orders") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="admin-list-page">
      <PageHeader description="查看充值单、钱包流水与 AI 用量明细" />
      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="orders">充值订单</TabsTrigger>
          {canReadFinance ? <><TabsTrigger value="ledger">钱包流水</TabsTrigger>
          <TabsTrigger value="usage">用量明细</TabsTrigger></> : null}
        </TabsList>
        <TabsContent value="orders" className="space-y-4">
          <AdminFilterBar>
            <Select value={orderStatus} onChange={(e) => setOrderStatus(e.target.value)}>
              <option value="">全部状态</option>
              <option value="pending">待支付</option>
              <option value="paid">已支付</option>
              <option value="closed">已关闭</option>
            </Select>
            <AdminUserSearchSelect value={orderUserId} onChange={(id) => setOrderUserId(id)} />
            <Button
              size="sm"
              variant="secondary"
              className="admin-filter-action"
              onClick={() => {
                if (orderPage === 1) void loadOrders(1);
                else setOrderPage(1);
              }}
            >
              筛选
            </Button>
          </AdminFilterBar>
          <AdminListState loading={orderRequest.loading} error={orderRequest.error} empty={!orders?.items.length} emptyTitle="暂无匹配订单" onRetry={() => void loadOrders()}>
          <div className="rounded-lg border bg-background">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>商户单号</TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead>金额</TableHead>
                  <TableHead>入账</TableHead>
                  <TableHead>支付</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>渠道单号</TableHead>
                  <TableHead>支付时间</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(orders?.items ?? []).map((o) => (
                  <TableRow
                    key={o.id}
                    className="cursor-pointer"
                    onClick={() => {
                      setOrderDetail(o);
                      orderQuery.open(o.id);
                    }}
                  >
                    <TableCell>{o.id}</TableCell>
                    <TableCell className="font-mono text-xs">{o.out_trade_no}</TableCell>
                    <TableCell>
                      <AdminEntityLink kind="user" id={o.user_id} label={o.user_email ?? undefined} />
                    </TableCell>
                    <TableCell>{o.sku_id}</TableCell>
                    <TableCell>¥{fenToYuan(o.amount_fen)}</TableCell>
                    <TableCell>¥{fenToYuan(o.credit_fen)}</TableCell>
                    <TableCell>{payTypeLabel(o.pay_type)}</TableCell>
                    <TableCell>
                      <Badge variant={o.status === "paid" ? "success" : "secondary"}>
                        {orderStatusLabel(o.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{o.trade_no || "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {o.paid_at ? new Date(o.paid_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(o.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          </AdminListState>
          {!orderRequest.loading && !orderRequest.error && orders && (
            <PaginationBar
              page={orders.meta.page}
              pageSize={orders.meta.page_size}
              total={orders.meta.total}
              onPageChange={setOrderPage}
            />
          )}
        </TabsContent>
        <TabsContent value="ledger" className="space-y-4">
          <AdminFilterBar>
            <Select value={ledgerKind} onChange={(e) => setLedgerKind(e.target.value)}>
              <option value="">全部类型</option>
              <option value="topup">充值</option>
              <option value="grant">赠送</option>
              <option value="adjust">调账</option>
              <option value="freeze">冻结</option>
              <option value="unfreeze">解冻</option>
              <option value="settle">结算</option>
              <option value="refund">退款</option>
            </Select>
            <AdminUserSearchSelect value={ledgerUserId} onChange={(id) => setLedgerUserId(id)} />
            <Button
              size="sm"
              variant="secondary"
              className="admin-filter-action"
              onClick={() => {
                if (ledgerPage === 1) void loadLedger(1);
                else setLedgerPage(1);
              }}
            >
              筛选
            </Button>
          </AdminFilterBar>
          <AdminListState loading={ledgerRequest.loading} error={ledgerRequest.error} empty={!ledger?.items.length} emptyTitle="暂无匹配流水" onRetry={() => void loadLedger()}>
          <div className="rounded-lg border bg-background">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>变动</TableHead>
                  <TableHead>余额后</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>关联</TableHead>
                  <TableHead>备注</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(ledger?.items ?? []).map((e) => (
                  <TableRow key={e.id} className="cursor-pointer" onClick={() => setLedgerDetail(e)}>
                    <TableCell>{e.id}</TableCell>
                    <TableCell>
                      <AdminEntityLink kind="user" id={e.user_id} label={e.user_email ?? undefined} />
                    </TableCell>
                    <TableCell className={e.delta_fen >= 0 ? "text-emerald-700" : "text-red-600"}>
                      {e.delta_fen >= 0 ? "+" : ""}
                      ¥{fenToYuan(e.delta_fen)}
                    </TableCell>
                    <TableCell>¥{fenToYuan(e.balance_after)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{ledgerKindLabel(e.kind)}</Badge>
                    </TableCell>
                    <TableCell><LedgerRefLink row={e} /></TableCell>
                    <TableCell className="max-w-[200px] truncate">{e.note}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(e.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          </AdminListState>
          {!ledgerRequest.loading && !ledgerRequest.error && ledger && (
            <PaginationBar
              page={ledger.meta.page}
              pageSize={ledger.meta.page_size}
              total={ledger.meta.total}
              onPageChange={setLedgerPage}
            />
          )}
        </TabsContent>
        <TabsContent value="usage" className="space-y-4">
          <AdminFilterBar>
            <AdminUserSearchSelect value={usageUserId} onChange={(id) => setUsageUserId(id)} />
            <Input placeholder="任务 ID" value={usageTaskId} onChange={(e) => setUsageTaskId(e.target.value)} />
            <Select value={usageDomain} onChange={(e) => setUsageDomain(e.target.value)}>
              <option value="">全部领域</option>
              <option value="kepu">科普</option>
              <option value="drama">漫剧</option>
              <option value="studio">工作室</option>
              <option value="api">开放 API</option>
            </Select>
            <Input
              placeholder="billing_key"
              value={usageBillingKey}
              onChange={(e) => setUsageBillingKey(e.target.value)}
            />
            <Select value={usageCapability} onChange={(e) => setUsageCapability(e.target.value)}>
              <option value="">全部能力</option>
              <option value="llm">LLM 文本</option>
              <option value="image">生图</option>
              <option value="video">视频</option>
              <option value="tts">配音</option>
            </Select>
            <Input
              placeholder="模型（如 seedance-2.5）"
              value={usageModel}
              onChange={(e) => setUsageModel(e.target.value)}
            />
            <Select value={usageBasis} onChange={(e) => setUsageBasis(e.target.value)}>
              <option value="">全部计费依据</option>
              <option value="estimate">估算</option>
              <option value="upstream">实测（上游）</option>
              <option value="upstream_usage">实测(token)</option>
              <option value="upstream_cost">实测(费用)</option>
            </Select>
            <AdminDateRangeFilter
              from={usageDateFrom}
              to={usageDateTo}
              onChange={({ from, to }) => {
                setUsageDateFrom(from);
                setUsageDateTo(to);
              }}
            />
            <Button
              size="sm"
              variant="outline"
              className="admin-filter-action"
              onClick={() => {
                setUsageBillingKey("llm_chat");
                setUsageCapability("llm");
                setUsageModel("");
                if (usagePage === 1) void loadUsage(1, { billing_key: "llm_chat", capability: "llm", model: "" });
                else setUsagePage(1);
              }}
            >
              LLM 用量
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="admin-filter-action"
              onClick={() => {
                setUsageBillingKey("");
                setUsageCapability("video");
                setUsageModel("seedance-2.5");
                if (usagePage === 1) void loadUsage(1, { billing_key: "", capability: "video", model: "seedance-2.5" });
                else setUsagePage(1);
              }}
            >
              Seedance 2.5
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="admin-filter-action"
              onClick={() => {
                if (usagePage === 1) void loadUsage(1);
                else setUsagePage(1);
              }}
            >
              筛选
            </Button>
          </AdminFilterBar>
          <AdminListState loading={usageRequest.loading} error={usageRequest.error} empty={!usage?.items.length} emptyTitle="暂无匹配用量" onRetry={() => void loadUsage()}>
          <div className="rounded-lg border bg-background">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>任务</TableHead>
                  <TableHead>项目</TableHead>
                  <TableHead>领域</TableHead>
                  <TableHead>能力</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>扣费</TableHead>
                  <TableHead>上游成本</TableHead>
                  <TableHead>计费依据</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(usage?.items ?? []).map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell>
                      <AdminEntityLink kind="user" id={row.user_id} label={row.user_email ?? undefined} />
                    </TableCell>
                    <TableCell>
                      {row.task_run_id ? (
                        <AdminEntityLink kind="task" id={row.task_run_id} />
                      ) : (
                        "历史/未关联"
                      )}
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.project_id ? (
                        <AdminEntityLink kind="project" id={row.project_id} />
                      ) : row.drama_project_id ? (
                        <AdminEntityLink kind="drama" id={row.drama_project_id} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{row.domain ? taskDomainLabel(row.domain) : "—"}</TableCell>
                    <TableCell>{row.capability ?? row.billing_key}</TableCell>
                    <TableCell className="max-w-[120px] truncate text-xs">{row.model || "—"}</TableCell>
                    <TableCell>{row.total_tokens ?? 0}</TableCell>
                    <TableCell>¥{fenToYuan(row.charge_fen ?? 0)}</TableCell>
                    <TableCell>¥{fenToYuan(row.cost_fen ?? 0)}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          row.billing_basis === "estimate" || row.estimated
                            ? "secondary"
                            : "success"
                        }
                        title={
                          row.billing_basis === "upstream_cost"
                            ? "按 TokenFree 返回的实际费用扣费"
                            : row.billing_basis === "upstream_usage"
                              ? "按 TokenFree usage token × 官方单价扣费"
                              : "上游未返回 usage，按配置估算 token 扣费"
                        }
                      >
                        {row.billing_basis_label ?? (row.estimated ? "估算" : "实测")}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          </AdminListState>
          {!usageRequest.loading && !usageRequest.error && usage && (
            <PaginationBar
              page={usage.meta.page}
              pageSize={usage.meta.page_size}
              total={usage.meta.total}
              onPageChange={setUsagePage}
            />
          )}
        </TabsContent>
      </Tabs>

      <OrderDetailDialog
        orderDetail={orderDetail}
        open={orderQuery.isOpen}
        loading={orderDetailLoading}
        error={orderDetailError}
        onRetry={() => setOrderDetailRetry((value) => value + 1)}
        onClose={() => {
          setOrderDetail(null);
          setSearchParams((prev) => { const next = new URLSearchParams(prev); next.delete("order"); next.delete("trade"); return next; }, { replace: true });
        }}
      />
      <LedgerDetailDialog ledgerDetail={ledgerDetail} onClose={() => setLedgerDetail(null)} />
    </div>
  );
}
