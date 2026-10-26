/*
 * TOKEN_KEY localStorage key for JWT
 * USER_KEY cached admin profile
 */
const TOKEN_KEY = "admin_token";
const USER_KEY = "admin_user";

export type AdminUser = {
  id: number;
  email: string;
  nickname: string;
  role: string;
  plan: string;
  balance_fen: number;
  permissions?: string[];
};

// Read stored JWT
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

// Persist JWT
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

// Clear auth state
export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// Read cached user profile
export function getCachedUser(): AdminUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AdminUser;
  } catch {
    return null;
  }
}

// Cache user profile
export function setCachedUser(user: AdminUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

// Whether current cached user is admin
export function isAdminUser(user: AdminUser | null): boolean {
  return !!user && ["admin", "admin_readonly", "admin_operator", "admin_finance", "admin_reviewer"].includes(user.role);
}
