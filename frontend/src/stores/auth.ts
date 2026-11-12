import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login, changePassword } from '@/services/auth'
import { fetchMe } from '@/services/api'
import { ElMessage } from 'element-plus'
import type { LoginResponse } from '@/types/api'

let redirecting = false

export const useAuthStore = defineStore('auth', () => {
  const token = ref('')
  const role = ref('user')
  const isLoggedIn = computed(() => !!token.value)
  const justLoggedIn = ref(false)

  const username = ref('')

  // 模块顶层初始化，确保路由守卫执行前 token 已就绪
  token.value = localStorage.getItem('agnes2api_token') || ''
  role.value = localStorage.getItem('agnes2api_role') || 'user'

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('agnes2api_token', t)
  }

  function setRole(r: string) {
    role.value = r
    localStorage.setItem('agnes2api_role', r)
  }

  function setUsername(u: string) {
    username.value = u
  }

  function clearToken() {
    token.value = ''
    role.value = 'user'
    username.value = ''
    localStorage.removeItem('agnes2api_token')
    localStorage.removeItem('agnes2api_role')
  }

  async function loginAction(usernameStr: string, password: string): Promise<LoginResponse> {
    const res = await login(usernameStr, password)
    setToken(res.access_token)
    setRole(res.role)
    setUsername(usernameStr)
    justLoggedIn.value = true
    return res
  }

  async function logout() {
    clearToken()
    redirecting = false
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
      setRole(me.role)
    } catch {
      // ignore
    }
  }

  return {
    token,
    role,
    username,
    isLoggedIn,
    justLoggedIn,
    setToken,
    setRole,
    setUsername,
    clearToken,
    loginAction,
    logout,
    changePasswordAction,
    fetchUserInfo,
  }
})
