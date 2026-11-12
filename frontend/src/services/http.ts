import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import type { ApiError } from '@/types/errors'
import { getErrorMessage } from '@/utils/errorMessage'

let isRedirecting = false

const http = axios.create({
  baseURL: '/api/manage',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('agnes2api_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error: ApiError) => {
    if (error.response?.status === 401 && !isRedirecting) {
      isRedirecting = true
      const authStore = useAuthStore()
      authStore.clearToken()
      window.location.href = '/login'
      ElMessage.error('会话已过期，请重新登录')
    } else {
      const msg = getErrorMessage(error, '请求失败')
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default http
