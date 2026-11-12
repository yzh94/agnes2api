import type { ApiError } from '@/types/errors'

const STATUS_TEXT: Record<number, string> = {
  400: '请求参数错误',
  401: '未认证或登录已过期，请重新登录',
  403: '没有权限执行此操作',
  404: '请求的资源不存在',
  409: '操作冲突，请稍后重试',
  413: '上传内容过大',
  422: '请求参数校验失败',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务暂不可用，请稍后重试',
  504: '网关超时，请稍后重试',
}

const MESSAGE_RULES: Array<[RegExp, string]> = [
  [/not authenticated/i, '未认证或登录已过期，请重新登录'],
  [/could not validate credentials/i, '登录凭证校验失败，请重新登录'],
  [/invalid token/i, '登录凭证无效，请重新登录'],
  [/incorrect username or password/i, '用户名或密码错误'],
  [/inactive user/i, '账号已被停用，请联系管理员'],
  [/not authorized/i, '没有权限执行此操作'],
  [/permission denied/i, '没有权限执行此操作'],
  [/forbidden/i, '没有权限执行此操作'],
  [/not found/i, '请求的资源不存在'],
  [/username already taken/i, '该用户名已被占用'],
  [/already exists/i, '该记录已存在'],
  [/cannot delete yourself/i, '不能删除当前登录的账号'],
  [/model name already exists/i, '该模型名称已存在'],
  [/invalid status/i, '无效的状态值'],
  [/invalid or expired state parameter/i, '授权参数无效或已过期'],
  [/failed to exchange discord code/i, 'Discord 授权码换取失败'],
  [/failed to get discord user information/i, '获取 Discord 用户信息失败'],
  [/discord username conflict/i, '该 Discord 账号已绑定其他用户，请联系管理员'],
  [/discord oauth not configured/i, 'Discord 登录尚未配置，请联系管理员'],
  [/field required/i, '缺少必填参数'],
  [/string too short/i, '输入内容过短'],
  [/string too long/i, '输入内容过长'],
  [/value is not a valid integer/i, '参数必须为整数'],
  [/value is not a valid (boolean|bool)/i, '参数必须为布尔值'],
  [/value is not a valid float/i, '参数必须为数字'],
  [/value is not a valid email/i, '邮箱格式不正确'],
  [/network error/i, '网络连接失败，请检查网络后重试'],
  [/timeout of \d+ms exceeded/i, '请求超时，请稍后重试'],
  [/request aborted/i, '请求已取消'],
]

function extractRawMessage(err: unknown): { status?: number; raw?: string } {
  const e = err as ApiError
  const status = e?.response?.status
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return { status, raw: detail }
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined
    if (first && typeof first.msg === 'string') return { status, raw: first.msg }
  }
  return { status, raw: e?.message }
}

export function getErrorMessage(err: unknown, fallback = '请求失败'): string {
  const { status, raw } = extractRawMessage(err)
  if (raw) {
    if (/[\u4e00-\u9fa5]/.test(raw)) return raw
    for (const [pattern, zh] of MESSAGE_RULES) {
      if (pattern.test(raw)) return zh
    }
    const codeMatch = raw.match(/request failed with status code (\d+)/i)
    const code = codeMatch ? Number(codeMatch[1]) : status
    if (code && STATUS_TEXT[code]) return STATUS_TEXT[code]
    return fallback
  }
  if (status && STATUS_TEXT[status]) return STATUS_TEXT[status]
  return fallback
}
