<template>
  <div class="login-container">
    <div class="bg-grid"></div>
    <div class="login-layout">
      <el-card class="login-card" shadow="never">
        <div class="login-header">
          <BrandLogo size="lg" />
          <h2 class="login-title">欢迎回来</h2>
          <p class="login-subtitle">登录以继续管理您的 API</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin" size="large" class="login-form">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="请输入账号" :prefix-icon="User" autofocus />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password @keyup.enter="handleLogin" :prefix-icon="Lock" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">登录</el-button>
          </el-form-item>
          <div class="discord-divider">
            <span class="divider-line"></span>
            <span>或</span>
            <span class="divider-line"></span>
          </div>
          <el-button class="discord-btn" :loading="discordLoading" @click="handleDiscordLogin">
            <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 5.424 1.793 9.317 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
            </svg>
            使用 Discord 登录
          </el-button>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import BrandLogo from '@/components/BrandLogo.vue'
import { getDiscordAuthUrl } from '@/services/discord'
import { getErrorMessage } from '@/utils/errorMessage'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const discordLoading = ref(false)

const form = ref({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await authStore.loginAction(form.value.username, form.value.password)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } catch (err: any) {
      ElMessage.error(getErrorMessage(err, '登录失败'))
    } finally {
      loading.value = false
    }
  })
}

async function handleDiscordLogin() {
  if (discordLoading.value) return
  discordLoading.value = true
  try {
    const state = crypto.randomUUID()
    const { authorize_url } = await getDiscordAuthUrl(state)
    const popupWidth = 480
    const popupHeight = 600
    const left = window.screenX + (window.outerWidth - popupWidth) / 2
    const top = window.screenY + (window.outerHeight - popupHeight) / 2
    const popup = window.open(authorize_url, 'discord_auth', `width=${popupWidth},height=${popupHeight},left=${left},top=${top},popup`)
    if (!popup) {
      ElMessage.error('弹出窗口被拦截，请允许后重试')
      discordLoading.value = false
      return
    }
    let authComplete = false
    const handler = (event: MessageEvent) => {
      if (event.data?.type !== 'DISCORD_AUTH_SUCCESS' || authComplete) return
      authComplete = true
      window.removeEventListener('message', handler)
      const { token, role, username } = event.data
      localStorage.setItem('agnes2api_token', token)
      localStorage.setItem('agnes2api_role', role)
      localStorage.setItem('agnes2api_username', username)
      authStore.setToken(token)
      authStore.setRole(role)
      authStore.setUsername(username)
      discordLoading.value = false
      ElMessage.success('登录成功')
      router.push('/dashboard')
    }
    window.addEventListener('message', handler)
    const poll = setInterval(() => {
      if (popup.closed) {
        clearInterval(poll)
        window.removeEventListener('message', handler)
        if (!authComplete && discordLoading.value) {
          discordLoading.value = false
          ElMessage.error('授权已取消')
        }
      }
    }, 500)
  } catch (err: any) {
    const msg = getErrorMessage(err, '获取 Discord 授权链接失败')
    ElMessage.error(msg)
    discordLoading.value = false
  }
}
</script>

<style scoped src="@/styles/auth-page.css"></style>
