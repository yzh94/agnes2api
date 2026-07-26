<template>
  <div class="app-layout">
    <!-- 移动端遮罩 -->
    <div v-if="isMobile && sidebarVisible" class="sidebar-overlay" @click="sidebarVisible = false" />

    <!-- 移动端顶部导航栏 -->
    <div class="mobile-header" v-if="isMobile">
      <el-button text @click="sidebarVisible = true">
        <el-icon><Menu /></el-icon>
      </el-button>
      <span class="mobile-page-title">{{ pageTitle }}</span>
      <div class="mobile-header-actions">
        <el-button text @click="pwdDialogVisible = true">
          <el-icon><Lock /></el-icon>
        </el-button>
        <el-button text type="danger" @click="authStore.logout()">
          <el-icon><SwitchButton /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 侧边栏抽屉（移动端） -->
    <el-drawer v-if="isMobile" v-model="sidebarVisible" :show-close="false" size="280px" class="mobile-sidebar-drawer">
      <div class="brand">
        <div class="logo-box">A2</div>
        Agnes2API
      </div>
      <el-menu
        :default-active="activeRoute"
        class="nav-menu"
        @select="(index: string) => { handleNavSelect(index); sidebarVisible = false }"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/keys">
          <el-icon><Key /></el-icon>
          <span>授权密钥</span>
        </el-menu-item>
        <el-menu-item index="/upstream">
          <el-icon><Connection /></el-icon>
          <span>上游通道</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <!-- 桌面端侧边栏 -->
    <el-aside width="240px" class="sidebar" v-if="!isMobile">
      <div class="brand">
        <div class="logo-box">A2</div>
        Agnes2API
      </div>
      <el-menu
        :default-active="activeRoute"
        class="nav-menu"
        @select="handleNavSelect"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/keys">
          <el-icon><Key /></el-icon>
          <span>授权密钥</span>
        </el-menu-item>
        <el-menu-item index="/upstream">
          <el-icon><Connection /></el-icon>
          <span>上游通道</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <div class="main-content">
      <el-header class="header" v-if="!isMobile">
        <div class="header-left">
          <h2 class="page-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <span class="user-info">{{ authStore.username }}</span>
          <el-button text @click="pwdDialogVisible = true">
            <el-icon class="el-icon--left"><Lock /></el-icon>修改密码
          </el-button>
          <el-button type="danger" text @click="authStore.logout()">
            <el-icon class="el-icon--left"><SwitchButton /></el-icon>退出登录
          </el-button>
        </div>
      </el-header>

      <div class="content-body">
        <router-view />
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="pwdDialogVisible" title="修改密码" width="400px">
      <el-form ref="pwdFormRef" @submit.prevent="handleChangePassword" label-position="top">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="handleChangePassword">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { ElFormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { DataLine, Key, Connection, Lock, SwitchButton, Menu } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const pwdDialogVisible = ref(false)
const pwdFormRef = ref<ElFormInstance>()
const pwdForm = ref({ old: '', new: '', confirm: '' })
const pwdSubmitting = ref(false)

const activeRoute = computed(() => route.path)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/dashboard': '全局模型成功率看板',
    '/keys': '授权密钥管理',
    '/upstream': '上游通道配置',
  }
  return titles[route.path] || ''
})

async function handleChangePassword() {
  if (!pwdForm.value.old || !pwdForm.value.new || !pwdForm.value.confirm) {
    ElMessage.warning('请填写完整信息')
    return
  }
  if (pwdForm.value.new !== pwdForm.value.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdSubmitting.value = true
  try {
    await authStore.changePasswordAction(pwdForm.value.old, pwdForm.value.new)
  } finally {
    pwdSubmitting.value = false
  }
}

function handleNavSelect(index: string) {
  router.push(index)
}

// 移动端检测
const isMobile = ref(false)
const sidebarVisible = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

/* ========== 桌面端侧边栏 ========== */
.sidebar {
  background: var(--el-bg-color-overlay);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}

.brand {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-light);
}

.logo-box {
  background: var(--el-color-primary);
  color: #fff;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
  margin-right: 12px;
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.4);
}

.nav-menu {
  flex: 1;
  background: transparent;
  border: none;
  padding: 12px 8px;
}

.nav-menu .el-menu-item {
  color: var(--el-text-color-regular);
  height: 48px;
  line-height: 48px;
  border-radius: 8px;
  margin-bottom: 4px;
}

.nav-menu .el-menu-item:hover {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.nav-menu .el-menu-item.is-active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 500;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.header {
  height: 64px;
  background: var(--el-bg-color-overlay);
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0;
}

.user-info {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-right: 16px;
}

.content-body {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
}

/* ========== 移动端适配 ========== */
.mobile-header {
  height: 56px;
  background: var(--el-bg-color-overlay);
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.mobile-page-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 50%;
}

.mobile-header-actions {
  display: flex;
  gap: 4px;
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
}

:deep(.mobile-sidebar-drawer .el-drawer__header) {
  display: none;
}

:deep(.mobile-sidebar-drawer .el-drawer__body) {
  padding: 0;
}

@media (max-width: 768px) {
  .app-layout {
    flex-direction: column;
    min-height: 100dvh;
  }

  .main-content {
    width: 100%;
    min-height: 0;
  }

  .content-body {
    padding: 12px 16px;
    width: 100%;
  }

  .mobile-header {
    width: 100%;
    flex-shrink: 0;
  }

  .mobile-header .el-button {
    flex-shrink: 0;
  }

  .mobile-header-actions {
    flex-shrink: 0;
  }
}

@media (max-width: 480px) {
  .content-body {
    padding: 12px 12px;
  }
  .mobile-page-title {
    flex: 1;
    max-width: none;
    min-width: 0;
    margin: 0 8px;
  }
}
</style>
