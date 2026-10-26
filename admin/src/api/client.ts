import { clearAuth, getToken, isAdminUser, setCachedUser, setToken, type AdminUser } from "@/lib/auth";
import { sessionLoginRedirect } from "@/lib/authRedirect";

type ApiError = {
  detail?: string | { msg?: string }[];
};

// 将 FastAPI 的校验错误或业务错误转换为可读文案
function errorMessage(data: ApiError, status: number): string {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return `请求失败 (${status})`;
}

// 为管理接口附加会话信息，统一处理响应与登录失效
export async function adminFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...options, headers });
  // 登录 401 = 账号密码错误；其它 401 = 会话失效
  const isLoginRequest = path.includes("/api/auth/login");
  if (res.status === 401 && !isLoginRequest) {
    clearAuth();
    const redirect = sessionLoginRedirect(window.location.pathname, window.location.search, window.location.hash, import.meta.env.BASE_URL);
    if (redirect) window.location.href = redirect;
    throw new Error("未登录或登录已失效");
  }
  return res;
}

/** JSON 接口与文件下载共用身份校验；代理错误页不直接抛 JSON 解析异常。 */
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, options);
  const text = await res.text();
  let data: ApiError & T = {} as ApiError & T;
  try { if (text) data = JSON.parse(text) as ApiError & T; } catch {
    if (res.ok) throw new Error("服务返回了无法识别的数据，请重试");
  }
  if (!res.ok) {
    throw new Error(errorMessage(data as ApiError, res.status));
  }
  return data as T;
}

// 登录后读取用户资料并验证管理员权限
export async function loginAsAdmin(email: string, password: string): Promise<AdminUser> {
  const tokenRes = await api<{ access_token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(tokenRes.access_token);
  let me: AdminUser;
  try { me = await api<AdminUser>("/api/auth/me"); } catch (error) { clearAuth(); throw error; }
  if (!isAdminUser(me)) {
    clearAuth();
    throw new Error("该账号没有管理员权限");
  }
  setCachedUser(me);
  return me;
}

// 保持既有导入路径兼容，新增接口类型按领域存放在 types/。
export type * from "./types/common";
export type * from "./types/analytics";
export type * from "./types/finance";
export type * from "./types/projects";
export type * from "./types/tasks";
export type * from "./types/settings";
