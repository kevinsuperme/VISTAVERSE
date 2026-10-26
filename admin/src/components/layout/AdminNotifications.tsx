import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { AdminModal } from "@/components/admin/AdminModal";
import { Button } from "@/components/ui/button";
import { PaginationBar } from "@/components/PaginationBar";
import { safeNextPath } from "@/lib/authRedirect";

type Notification = { id: string; kind: string; severity: string; title: string; message: string; href: string; created_at: string; read: boolean };
type Response = { items: Notification[]; meta: { page: number; page_size: number; total: number }; unread_count: number };

export function AdminNotifications() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const sequence = useRef(0);
  const locked = useRef(false);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true); setError("");
    try {
      const result = await api<Response>(`/api/admin/notifications?page=${page}&page_size=20&unread_only=${unreadOnly}`);
      if (request === sequence.current) {
        setData(result);
        const lastPage = Math.max(1, Math.ceil(result.meta.total / 20));
        if (page > lastPage) setPage(lastPage);
      }
    } catch (err) { if (request === sequence.current) setError(err instanceof Error ? err.message : "通知加载失败"); }
    finally { if (request === sequence.current) setLoading(false); }
  }, [page, unreadOnly]);
  useEffect(() => { void load(); return () => { sequence.current += 1; }; }, [load, open]);
  async function markRead(ids: string[]) {
    if (!ids.length || locked.current) return false;
    locked.current = true; setPending(true);
    try { await api("/api/admin/notifications/read", { method: "PATCH", body: JSON.stringify({ ids }) }); await load(); return true; }
    catch (err) { toast.error(err instanceof Error ? err.message : "标记失败，请重试"); return false; }
    finally { locked.current = false; setPending(false); }
  }
  async function visit(item: Notification) {
    if (!item.read && !await markRead([item.id])) return;
    setOpen(false); navigate(safeNextPath(item.href));
  }
  return <>
    <button type="button" className="admin-icon-btn relative" onClick={() => setOpen(true)} aria-label={`通知中心${data?.unread_count ? `，${data.unread_count} 条未读` : ""}`}>
      <Bell className="h-4 w-4" />{(data?.unread_count ?? 0) > 0 && <span className="admin-notification-dot" aria-hidden="true" />}
    </button>
    <AdminModal presentation="drawer" open={open} onOpenChange={setOpen} title="通知中心" subtitle="待审核作品、失败任务与运行异常" size="lg" busy={pending}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <label className="flex items-center gap-2"><input type="checkbox" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1); }} />仅看未读</label>
        <Button size="sm" variant="outline" disabled={pending || loading || !data?.items.some((item) => !item.read)} onClick={() => void markRead((data?.items ?? []).filter((item) => !item.read).map((item) => item.id))}>本页标记已读</Button>
      </div>
      {loading ? <p role="status">正在加载通知…</p> : error ? <div role="alert"><p>{error}</p><Button variant="outline" onClick={() => void load()}>重试</Button></div> : data?.items.length ? <ul className="admin-notifications">
        {data.items.map((item) => <li key={item.id} className={item.read ? "is-read" : ""}>
          <button type="button" disabled={pending} onClick={() => void visit(item)}>
            <span className="flex gap-2 items-center"><strong>{item.title}</strong><span className="text-xs">{item.read ? "已读" : "未读"}</span></span>
            <span>{item.message}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
          </button>
        </li>)}
      </ul> : <p role="status">{unreadOnly ? "暂无未读通知" : "暂无待处理通知"}</p>}
      <PaginationBar page={page} pageSize={20} total={data?.meta.total ?? 0} onPageChange={setPage} />
    </AdminModal>
  </>;
}
