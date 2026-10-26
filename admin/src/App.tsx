import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { RequireAdmin } from "@/components/admin/RequireAdmin";
import { AdminRouteBoundary } from "@/components/admin/AdminRouteBoundary";
import { hasPermission } from "@/lib/permissions";
const AdjustRecordsPage = lazy(() => import("@/pages/AdjustRecordsPage").then((m) => ({ default: m.AdjustRecordsPage })));
const FinanceListPage = lazy(() => import("@/pages/FinanceListPage").then((m) => ({ default: m.FinanceListPage })));
const DashboardPage = lazy(() => import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const LoginPage = lazy(() => import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const OrdersPage = lazy(() => import("@/pages/OrdersPage").then((m) => ({ default: m.OrdersPage })));
const ProjectsPage = lazy(() => import("@/pages/ProjectsPage").then((m) => ({ default: m.ProjectsPage })));
const DramaProjectsPage = lazy(() => import("@/pages/DramaProjectsPage").then((m) => ({ default: m.DramaProjectsPage })));
const DramaAssetDetailPage = lazy(() => import("@/pages/drama/DramaAssetDetailPage").then((m) => ({ default: m.DramaAssetDetailPage })));
const DramaAssetsPage = lazy(() => import("@/pages/drama/DramaAssetsPage").then((m) => ({ default: m.DramaAssetsPage })));
const DramaEpisodeDetailPage = lazy(() => import("@/pages/drama/DramaEpisodeDetailPage").then((m) => ({ default: m.DramaEpisodeDetailPage })));
const DramaEpisodesPage = lazy(() => import("@/pages/drama/DramaEpisodesPage").then((m) => ({ default: m.DramaEpisodesPage })));
const DramaFragmentDetailPage = lazy(() => import("@/pages/drama/DramaFragmentDetailPage").then((m) => ({ default: m.DramaFragmentDetailPage })));
const DramaFragmentsPage = lazy(() => import("@/pages/drama/DramaFragmentsPage").then((m) => ({ default: m.DramaFragmentsPage })));
const DramaProjectDetailPage = lazy(() => import("@/pages/drama/DramaProjectDetailPage").then((m) => ({ default: m.DramaProjectDetailPage })));
const QueuesPage = lazy(() => import("@/pages/QueuesPage").then((m) => ({ default: m.QueuesPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const TemplatesPage = lazy(() => import("@/pages/TemplatesPage").then((m) => ({ default: m.TemplatesPage })));
const UsersPage = lazy(() => import("@/pages/UsersPage").then((m) => ({ default: m.UsersPage })));
const WorksPage = lazy(() => import("@/pages/WorksPage").then((m) => ({ default: m.WorksPage })));
function Page({ permission, children }: { permission: string; children: ReactNode }) {
  const location = useLocation();
  if (permission === "dashboard:read" && !hasPermission(permission) && hasPermission("works:read")) return <Navigate to="/works" replace />;
  if (!hasPermission(permission)) return <div className="admin-route-state" role="alert"><h2>没有访问权限</h2><p>当前角色无法访问此功能，请联系超级管理员分配权限。</p><Link to="/">返回仪表盘</Link></div>;
  return <AdminRouteBoundary key={location.pathname}><Suspense fallback={<div className="admin-route-state" role="status">正在加载页面…</div>}>{children}</Suspense></AdminRouteBoundary>;
}

// Admin app routes
export default function App() {
  return (
    <Suspense fallback={<div className="admin-route-state" role="status">正在加载…</div>}><Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAdmin />}>
        <Route element={<AdminLayout />}>
          <Route index element={<Page permission="dashboard:read"><DashboardPage /></Page>} />
          <Route path="users" element={<Page permission="users:read"><UsersPage /></Page>} />
          <Route path="orders" element={<Page permission="orders:read"><OrdersPage /></Page>} />
          <Route path="adjustments" element={<Page permission="finance:read"><AdjustRecordsPage /></Page>} />
          <Route path="finance" element={<Page permission="finance:read"><FinanceListPage /></Page>} />
          <Route path="projects" element={<Page permission="content:read"><ProjectsPage /></Page>} />
          <Route path="drama-projects" element={<Page permission="content:read"><DramaProjectsPage /></Page>} />
          <Route path="drama-projects/:projectId" element={<Page permission="content:read"><DramaProjectDetailPage /></Page>} />
          <Route path="drama-assets" element={<Page permission="content:read"><DramaAssetsPage /></Page>} />
          <Route path="drama-assets/:assetId" element={<Page permission="content:read"><DramaAssetDetailPage /></Page>} />
          <Route path="drama-episodes" element={<Page permission="content:read"><DramaEpisodesPage /></Page>} />
          <Route path="drama-episodes/:episodeId" element={<Page permission="content:read"><DramaEpisodeDetailPage /></Page>} />
          <Route path="drama-fragments" element={<Page permission="content:read"><DramaFragmentsPage /></Page>} />
          <Route path="drama-fragments/:fragmentId" element={<Page permission="content:read"><DramaFragmentDetailPage /></Page>} />
          <Route path="works" element={<Page permission="works:read"><WorksPage /></Page>} />
          <Route path="templates" element={<Page permission="templates:read"><TemplatesPage /></Page>} />
          <Route path="queues" element={<Page permission="tasks:read"><QueuesPage /></Page>} />
          <Route path="settings" element={<Page permission="settings:read"><SettingsPage /></Page>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes></Suspense>
  );
}
