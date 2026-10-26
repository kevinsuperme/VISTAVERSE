/** Restrict post-login redirects to this admin SPA. */
export function safeNextPath(raw: string | null | undefined, fallback = '/') {
  if (!raw) return fallback
  const value = raw.trim()
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('://') || value.includes('\\')) return fallback
  if (/[\u0000-\u001f\u007f]/u.test(value)) return fallback
  return value
}

export function buildLoginRedirect(returnPath: string) {
  return `/login?next=${encodeURIComponent(safeNextPath(returnPath))}`
}

/** 将浏览器的完整路径还原为 Router 内路径，并保留部署前缀。 */
export function sessionLoginRedirect(pathname: string, search: string, hash: string, baseUrl: string) {
  const base = baseUrl.replace(/\/$/, "");
  const path = base && pathname.startsWith(`${base}/`) ? pathname.slice(base.length) : pathname;
  if (path === "/login") return null;
  return `${base}${buildLoginRedirect(`${path}${search}${hash}`)}`;
}
