import { getCachedUser, type AdminUser } from "./auth";

export const ADMIN_ROLE_LABELS: Record<string, string> = {
  admin: "超级管理员", admin_readonly: "只读管理员", admin_operator: "运营管理员",
  admin_finance: "财务管理员", admin_reviewer: "内容审核员", user: "普通用户",
};

/** 仅负责界面可见性；服务端对每个请求独立鉴权。权限来自当前 /auth/me。 */
export function hasPermission(permission: string, user: AdminUser | null = getCachedUser()): boolean {
  return !!user && (user.role === "admin" || Boolean(user.permissions?.includes(permission)));
}
