/** Return a safe in-app path used after authentication. */
export function safeNextPath(raw: string | null | undefined, fallback = '/') {
  if (!raw) return fallback
  const value = raw.trim()
  // Only allow root-relative URLs. Protocol-relative and control-character
  // values can otherwise turn this into an open redirect.
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('://') || value.includes('\\')) return fallback
  if (/[\u0000-\u001f\u007f]/u.test(value)) return fallback
  return value
}

export function buildAuthRedirect(returnPath: string) {
  const safePath = safeNextPath(returnPath, '/')
  return `/auth?next=${encodeURIComponent(safePath)}`
}
