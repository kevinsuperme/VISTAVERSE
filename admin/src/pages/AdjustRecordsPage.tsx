import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { useAdminUrlState } from "@/hooks/useAdminUrlState";
import type { AdminLedger, PageResult } from "@/api/client";
import { listAdminLedger } from "@/api/finance";
import { AdminDateRangeFilter } from "@/components/admin/AdminDateRangeFilter";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { AdminFilterBar } from "@/components/admin/AdminFilterBar";
import { AdminUserSearchSelect } from "@/components/admin/AdminUserSearchSelect";
import { PageSection } from "@/components/admin/PageSection";
import { PaginationBar } from "@/components/PaginationBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fenToYuan } from "@/lib/utils";

type LedgerRes = PageResult<AdminLedger>;

type DirectionFilter = "" | "credit" | "debit";

/** 调账方向文案：正数为调增，负数为调减 */
function directionLabel(deltaFen: number): string {
  return deltaFen >= 0 ? "调增" : "调减";
}

/** 管理端手动调账记录：仅展示 ref_type=admin 的钱包流水 */
export function AdjustRecordsPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useAdminUrlState<number>("page", 1);
  const appliedUser = Number(params.get("user_id")) || null;
  const appliedDirection = params.get("direction") || "";
  const appliedFrom = params.get("from") || "";
  const appliedTo = params.get("to") || "";
  const [userId, setUserId] = useState<number | null>(appliedUser);
  const [direction, setDirection] = useState<DirectionFilter>(appliedDirection as DirectionFilter);
  const [dateFrom, setDateFrom] = useState(appliedFrom);
  const [dateTo, setDateTo] = useState(appliedTo);
  const { data, loading, error, run } = useAdminRequest<LedgerRes>();
  const load = useCallback(() => run(() => listAdminLedger(page, {
    refType: "admin", userId: appliedUser,
    kind: appliedDirection === "credit" ? "grant" : appliedDirection === "debit" ? "adjust" : "",
    dateFrom: appliedFrom, dateTo: appliedTo,
  })), [run, page, appliedUser, appliedDirection, appliedFrom, appliedTo]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setUserId(appliedUser); setDirection(appliedDirection as DirectionFilter); setDateFrom(appliedFrom); setDateTo(appliedTo); }, [appliedUser, appliedDirection, appliedFrom, appliedTo]);
  function applyFilters() {
    if (dateFrom && dateTo && dateFrom > dateTo) return;
    const next = new URLSearchParams();
    if (userId) next.set("user_id", String(userId));
    if (direction) next.set("direction", direction);
    if (dateFrom) next.set("from", dateFrom);
    if (dateTo) next.set("to", dateTo);
    if (next.toString() === params.toString()) void load();
    else setParams(next, { replace: true });
  }

  const rows = data?.items ?? [];

  return (
    <div className="admin-page">
      <PageHeader description="用户管理里手动改余额产生的调账流水，含操作人与备注" />

      <AdminFilterBar>
        <AdminUserSearchSelect value={userId} onChange={setUserId} />
        <Select
          aria-label="调账方向"
          value={direction}
          onChange={(e) => setDirection(e.target.value as DirectionFilter)}
        >
          <option value="">全部方向</option>
          <option value="credit">调增</option>
          <option value="debit">调减</option>
        </Select>
        <AdminDateRangeFilter
          from={dateFrom}
          to={dateTo}
          onChange={({ from, to }) => {
            setDateFrom(from);
            setDateTo(to);
          }}
        />
        <Button
          size="sm"
          variant="secondary"
          className="admin-filter-action"
          disabled={Boolean(dateFrom && dateTo && dateFrom > dateTo)}
          onClick={applyFilters}
        >
          筛选
        </Button>
      </AdminFilterBar>
      {dateFrom && dateTo && dateFrom > dateTo ? <p role="alert">开始日期不能晚于结束日期</p> : null}

      <PageSection
        title="手动调账记录"
        description={data ? `共 ${data.meta.total} 条` : undefined}
        bodyClassName="!pt-0"
      >
        <div className="admin-table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>时间</TableHead>
                <TableHead>用户</TableHead>
                <TableHead>方向</TableHead>
                <TableHead>变动</TableHead>
                <TableHead>余额后</TableHead>
                <TableHead>操作人</TableHead>
                <TableHead>备注</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="!text-center text-[var(--admin-muted)]">
                    加载中…
                  </TableCell>
                </TableRow>
              ) : error ? <TableRow><TableCell colSpan={8}><div role="alert">{error}<Button size="sm" variant="outline" onClick={() => void load()}>重新加载</Button></div></TableCell></TableRow> : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="!text-center text-[var(--admin-muted)]">
                    暂无手动调账记录
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-mono text-xs">{row.id}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(row.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <AdminEntityLink kind="user" id={row.user_id} label={row.user_email ?? undefined} />
                    </TableCell>
                    <TableCell>
                      <Badge variant={row.delta_fen >= 0 ? "success" : "secondary"}>
                        {directionLabel(row.delta_fen)}
                      </Badge>
                    </TableCell>
                    <TableCell className={row.delta_fen >= 0 ? "text-emerald-700" : "text-red-600"}>
                      {row.delta_fen >= 0 ? "+" : ""}¥{fenToYuan(row.delta_fen)}
                    </TableCell>
                    <TableCell>¥{fenToYuan(row.balance_after)}</TableCell>
                    <TableCell>
                      {row.ref_id && /^\d+$/.test(row.ref_id) ? (
                        <AdminEntityLink
                          kind="user"
                          id={Number(row.ref_id)}
                          label={row.operator_email ?? undefined}
                        />
                      ) : (
                        row.operator_email || "—"
                      )}
                    </TableCell>
                    <TableCell className="max-w-[240px] truncate" title={row.note || undefined}>
                      {row.note || "—"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        {data ? (
          <PaginationBar
            page={data.meta.page}
            pageSize={data.meta.page_size}
            total={data.meta.total}
            onPageChange={(next) => setPage(next)}
          />
        ) : null}
      </PageSection>
    </div>
  );
}
