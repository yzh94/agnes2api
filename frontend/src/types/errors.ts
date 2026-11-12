export interface ApiError {
  response?: {
    data?: { detail?: string }
    status?: number
  }
  message?: string
}

export function isApiError(err: unknown): err is ApiError {
  return typeof err === 'object' && err !== null && 'response' in err
}

export function getApiErrorMessage(err: ApiError): string {
  return err.response?.data?.detail || err.message || '请求失败'
}
