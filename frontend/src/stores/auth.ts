import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login, changePassword } from '@/services/auth'
import { fetchMe } from '@/services/api'
import { ElMessage } from 'element-plus'
import type { LoginResponse } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('agnes2api_token') || '')
  const isLoggedIn = computed(() => !!token.value)
  const role = ref('admin')

  const username = ref('')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('agnes2api_token', t)
  }

  function setUsername(u: string) {
    username.value = u
  }

  function setRole(r: string) {
    role.value = r
  }

  function clearToken() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('agnes2api_token')
  }

  async function loginAction(usernameStr: string, password: string): Promise<LoginResponse> {
    const res = await login(usernameStr, password)
    setToken(res.access_token)
    // 后端只返回 access_token，role 从 /me 获取
    setUsername(usernameStr)
    return res
  }

  async function logout() {
    clearToken()
    setRole('admin')
    window.location.href = '/login'
  }

  async function changePasswordAction(oldPassword: string, newPassword: string) {
    await changePassword(oldPassword, newPassword)
    ElMessage.success('密码修改成功，请重新登录')
    logout()
  }

  async function fetchUserInfo() {
    try {
      const me = await fetchMe()
      setUsername(me.username)
    } catch {
      // ignore
    }
  }

  return {
    token,
    username,
    role,
    isLoggedIn,
    setToken,
    setUsername,
    setRole,
    clearToken,
    loginAction,
    logout,
    changePasswordAction,
    fetchUserInfo,
  }
})
