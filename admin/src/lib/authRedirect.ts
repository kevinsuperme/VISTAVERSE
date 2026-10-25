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
