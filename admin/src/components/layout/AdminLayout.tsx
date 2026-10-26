import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Clapperboard,
  FileVideo,
  Film,
  Image,
  Layers,
  LayoutDashboard,
  ListVideo,
  LogOut,
  Maximize2,
  Menu,
  Receipt,
  Scale,
  Settings,
  Shapes,
  Users,
  Wallet,
} from "lucide-react";
import { clearAuth, getCachedUser } from "@/lib/auth";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { AdminNotifications } from "./AdminNotifications";
import { hasPermission, ADMIN_ROLE_LABELS } from "@/lib/permissions";
import { cn } from "@/lib/utils";
type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
  matchPrefix?: boolean;
  permission?: string;
};
type NavGroup = {
  label: string;
  items: NavItem[];
};
const navGroups: NavGroup[] = [
  {
    label: "概览",
    items: [{ to: "/", permission: "dashboard:read", label: "仪表盘", icon: LayoutDashboard, end: true }],
  },
  {
    label: "业务",
    items: [
      { to: "/users", permission: "users:read", label: "用户管理", icon: Users },
      { to: "/orders", permission: "orders:read", label: "订单流水", icon: Receipt },
      { to: "/adjustments", permission: "finance:read", label: "手动调账", icon: Scale },
      { to: "/finance", permission: "finance:read", label: "财务列表", icon: Wallet },
      { to: "/projects", permission: "content:read", label: "科普项目", icon: Clapperboard },
      { to: "/works", permission: "works:read", label: "作品审核", icon: FileVideo },
    ],
  },
  {
    label: "漫剧",
    items: [
      { to: "/drama-projects", permission: "content:read", label: "漫剧项目", icon: Film, matchPrefix: true },
      { to: "/drama-assets", permission: "content:read", label: "资产库", icon: Image, matchPrefix: true },
      { to: "/drama-episodes", permission: "content:read", label: "分集管理", icon: ListVideo, matchPrefix: true },
      { to: "/drama-fragments", permission: "content:read", label: "分镜管理", icon: Layers, matchPrefix: true },
    ],
  },
  {
    label: "资源",
    items: [
      { to: "/templates", permission: "templates:read", label: "模板管理", icon: Shapes },
      { to: "/queues", permission: "tasks:read", label: "任务中心", icon: Layers },
    ],
  },
  {
    label: "系统",
    items: [{ to: "/settings", permission: "settings:read", label: "系统设置", icon: Settings }],
  },
];
const titles: Record<string, string> = {
  "/": "仪表盘",
  "/users": "用户管理",
  "/orders": "订单流水",
  "/adjustments": "手动调账",
  "/finance": "财务列表",
  "/projects": "科普项目",
  "/drama-projects": "漫剧项目",
  "/drama-assets": "资产库",
  "/drama-episodes": "分集管理",
  "/drama-fragments": "分镜管理",
  "/works": "作品审核",
  "/templates": "模板管理",
  "/settings": "系统设置",
  "/queues": "任务中心",
};
function resolveTitle(pathname: string): string {
  if (pathname.startsWith("/drama-projects/")) return "漫剧项目详情";
  if (pathname.startsWith("/drama-assets/")) return "资产详情";
  if (pathname.startsWith("/drama-episodes/")) return "分集详情";
  if (pathname.startsWith("/drama-fragments/")) return "分镜详情";
  return titles[pathname] ?? "管理后台";
}
// Admin shell: dark sidebar + glass top bar
export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCachedUser();
  /*
   * collapsed sidebar collapsed state
   */
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 900px)").matches);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const close = () => { setIsMobile(media.matches); if (!media.matches) setMobileOpen(false); };
    media.addEventListener("change", close);
    return () => media.removeEventListener("change", close);
  }, []);
  // Logout and return to login
  function handleLogout() {
    clearAuth();
    navigate("/login");
  }
  const title = resolveTitle(location.pathname);
  const initial = (user?.nickname || user?.email || "A").slice(0, 1).toUpperCase();
  const visibleGroups = navGroups.map((group) => ({ ...group, items: group.items.filter((item) => !item.permission || hasPermission(item.permission)) })).filter((group) => group.items.length);
  const sidebarContent = (compact: boolean) => <>
        <div className="admin-brand" aria-label="万象影界 VISTAVERSE 管理后台">
          <img className="admin-brand-mark" src={`${import.meta.env.BASE_URL}favicon.svg`} alt="万象影界" width={38} height={38} />
          {!compact && (
            <div>
              <div className="admin-brand-name">万象影界</div>
              <div className="admin-brand-sub">VISTAVERSE · 管理后台</div>
            </div>
          )}
        </div>
        <nav className="admin-nav" aria-label="主导航">
          {visibleGroups.map((group) => (
            <div key={group.label} className="admin-nav-group">
              {!compact ? <div className="admin-nav-group-label">{group.label}</div> : null}
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end ?? !item.matchPrefix}
                  className={({ isActive }) =>
                    cn(
                      "admin-nav-item",
                      (isActive || (item.matchPrefix && location.pathname.startsWith(`${item.to}/`))) &&
                        "is-active",
                    )
                  }
                  title={item.label}
                  onClick={() => setMobileOpen(false)}
                >
                  <item.icon className="h-[18px] w-[18px] shrink-0" />
                  {!compact && <span>{item.label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="admin-user-card">
          <div className="admin-avatar">{initial}</div>
          {!compact && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-[#e8f0eb]">{user?.email}</div>
              <div className="text-xs text-[rgba(240,245,242,0.45)]">{ADMIN_ROLE_LABELS[user?.role ?? ""] ?? "管理员"}</div>
            </div>
          )}
          <button type="button" className="admin-icon-btn !text-[rgba(240,245,242,0.55)] hover:!text-[#e8f0eb]" onClick={handleLogout} title="退出登录" aria-label="退出登录">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
</>;
  return (
    <div className={cn("admin-app", collapsed && "is-collapsed", mobileOpen && "is-mobile-open")}>
      <a className="admin-skip-link" href="#admin-main-content">跳转到主要内容</a>
      <aside className="admin-sidebar admin-sidebar--desktop">{sidebarContent(collapsed)}</aside>
      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="admin-mobile-nav" aria-describedby={undefined} onCloseAutoFocus={(event) => { event.preventDefault(); menuButton.current?.focus(); }}>
          <DialogTitle className="sr-only">管理导航</DialogTitle>
          {sidebarContent(false)}
        </DialogContent>
      </Dialog>
      <div className="admin-main">
        <header className="admin-topbar">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="admin-icon-btn"
              ref={menuButton}
              onClick={() => {
                if (window.matchMedia("(max-width: 900px)").matches) {
                  setCollapsed(false);
                  setMobileOpen((v) => !v);
                } else {
                  setCollapsed((v) => !v);
                }
              }}
              aria-label={isMobile ? mobileOpen ? "关闭导航菜单" : "打开导航菜单" : collapsed ? "展开侧栏" : "折叠侧栏"}
              aria-expanded={isMobile ? mobileOpen : !collapsed}
            >
              <Menu className="h-4 w-4" />
            </button>
            <div>
              <h1 className="admin-topbar-title">{title}</h1>
              <div className="admin-topbar-crumb">VISTAVERSE · 运营管理</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {hasPermission("notifications:read") && <AdminNotifications />}
            <button
              type="button"
              className="admin-icon-btn"
              title="全屏"
              aria-label="切换全屏"
              onClick={() => {
                if (!document.fullscreenElement) void document.documentElement.requestFullscreen().catch(() => toast.error("当前浏览器未允许全屏"));
                else void document.exitFullscreen().catch(() => toast.error("退出全屏失败"));
              }}
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </header>
        <main id="admin-main-content" tabIndex={-1} className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
