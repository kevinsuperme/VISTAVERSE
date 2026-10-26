import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

type AdminListStateProps = {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyTitle?: string;
  onRetry: () => void;
  children: ReactNode;
};

/** Keep loading, failed requests and a successful empty result distinct. */
export function AdminListState({ loading, error, empty, emptyTitle = "暂无匹配数据", onRetry, children }: AdminListStateProps) {
  if (loading) return <div className="admin-empty admin-panel" role="status" aria-live="polite">正在加载…</div>;
  if (error) return (
    <div className="admin-empty admin-panel" role="alert">
      <div className="admin-empty-title">加载失败</div>
      <div className="admin-empty-desc">{error}</div>
      <Button size="sm" variant="outline" onClick={onRetry}>重新加载</Button>
    </div>
  );
  if (empty) return (
    <div className="admin-empty admin-panel" role="status">
      <div className="admin-empty-title">{emptyTitle}</div>
      <div className="admin-empty-desc">请调整筛选条件后重试。</div>
    </div>
  );
  return children;
}
