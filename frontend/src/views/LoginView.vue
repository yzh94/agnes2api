<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <div class="logo-box">A2</div>
        <h1 class="login-title">Agnes2API</h1>
        <div class="subtitle">单用户管理控制台</div>
      </div>

      <el-form @submit.prevent="handleLogin" size="large" class="login-form">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="请输入账号"
          >
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            show-password
            @keyup.enter="handleLogin"
          >
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }

  loading.value = true
  try {
    await authStore.loginAction(username.value, password.value)
    // 获取用户信息（role）
    await authStore.fetchUserInfo()
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '登录失败，请检查账号密码'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: var(--el-bg-color-page);
  position: relative;
  overflow: hidden;
}

/* 优雅的背景点缀 */
.login-container::before {
  content: '';
  position: absolute;
  top: -100px;
  right: -100px;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  filter: blur(100px);
  opacity: 0.1;
  z-index: 0;
}

.login-container::after {
  content: '';
  position: absolute;
  bottom: -100px;
  left: -100px;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: var(--el-color-success);
  filter: blur(100px);
  opacity: 0.05;
  z-index: 0;
}

.login-card {
  width: 420px;
  z-index: 2;
  position: relative;
  border-radius: 12px !important;
  padding: 20px 10px;
}

@media (max-width: 480px) {
  .login-card {
    width: calc(100vw - 32px);
    margin: 0 16px;
  }
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo-box {
  background: var(--el-color-primary);
  color: #fff;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 16px;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.login-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin: 0 0 8px 0;
  letter-spacing: 1px;
}

.subtitle {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.login-form {
  padding: 0 20px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  margin-top: 16px;
  border-radius: 8px;
}

  register-link {
    display: none;
  }
</style>