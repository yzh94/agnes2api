export function maskKey(key: string, showStart = 6, showEnd = 4): string {
  if (key.length <= showStart + showEnd) return key
  return key.substring(0, showStart) + '...' + key.substring(key.length - showEnd)
}
