export function safeParseJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    const parsed = JSON.parse(raw)
    return parsed !== null && typeof parsed === 'object' ? (parsed as T) : fallback
  } catch {
    return fallback
  }
}
