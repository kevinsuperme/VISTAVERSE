/** Allow only web URLs for values that are opened in a new browser window. */
export function safeExternalUrl(raw: string | null | undefined): string {
  const value = (raw || '').trim()
  if (!value) return ''
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : ''
  } catch {
    return ''
  }
}
