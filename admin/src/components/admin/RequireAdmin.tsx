import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { api } from "@/api/client";
import { clearAuth, getToken, isAdminUser, setCachedUser, type AdminUser } from "@/lib/auth";
import { buildLoginRedirect } from "@/lib/authRedirect";
import { Button } from "@/components/ui/button";

/** 启动时向服务端确认身份，不信任缓存中可能过期的权限。 */
export function RequireAdmin() {
  const location = useLocation();
  const token = getToken();
  const [status, setStatus] = useState<"loading" | "ready" | "denied" | "error">("loading");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [verifiedToken, setVerifiedToken] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    if (!token) return;
    api<AdminUser>("/api/auth/me").then((user) => {
      if (!active) return;
      setVerifiedToken(token);
      if (!isAdminUser(user)) { clearAuth(); setStatus("denied"); return; }
      setCachedUser(user); setStatus("ready");
    }).catch((err: unknown) => {
      if (!active) return;
      setVerifiedToken(token);
      setError(err instanceof Error ? err.message : "身份校验失败"); setStatus("error");
    });
    return () => { active = false; };
  }, [token, attempt]);
  if (!token || (verifiedToken === token && status === "denied")) return <Navigate replace to={buildLoginRedirect(`${location.pathname}${location.search}${location.hash}`)} />;
  if (verifiedToken !== token) return <div className="admin-route-state" role="status">正在验证管理权限…</div>;
  if (status === "error") return <div className="admin-route-state" role="alert"><p>{error}</p>
    <Button onClick={() => { setStatus("loading"); setAttempt((value) => value + 1); }}>重试身份校验</Button>
    <Button variant="outline" onClick={() => { clearAuth(); setStatus("denied"); }}>返回登录</Button>
  </div>;
  if (status !== "ready") return <div className="admin-route-state" role="status">正在验证管理权限…</div>;
  return <Outlet />;
}
