<template>
  <div class="app-layout">
    <!-- 移动端遮罩 -->
    <div v-if="isMobile && sidebarVisible" class="sidebar-overlay" @click="sidebarVisible = false" />

    <!-- 移动端顶部导航 -->
    <div class="mobile-header" v-if="isMobile">
      <el-button text @click="sidebarVisible = true" class="mobile-menu-btn">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </el-button>
      <span class="mobile-page-title">{{ pageTitle }}</span>
      <div class="mobile-header-actions">
        <el-button text @click="announcementStore.openForReview()"><el-icon><Bell /></el-icon></el-button>
        <el-button text @click="pwdStore.showModal = true"><el-icon><Lock /></el-icon></el-button>
        <el-button text type="danger" @click="authStore.logout()"><el-icon><SwitchButton /></el-icon></el-button>
      </div>
    </div>

    <!-- 移动端侧边栏抽屉 -->
    <el-drawer v-if="isMobile" v-model="sidebarVisible" :show-close="false" size="280px" class="mobile-sidebar-drawer">
      <div class="brand">
        <BrandLogo size="md" />
        <span class="brand-text">AGNES2API</span>
      </div>
      <el-menu :default-active="activeRoute" class="nav-menu" @select="(index: string) => { handleNavSelect(index); sidebarVisible = false }">
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon><span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/keys">
          <el-icon><Key /></el-icon><span>授权密钥</span>
        </el-menu-item>
        <el-menu-item index="/upstream">
          <el-icon><Connection /></el-icon><span>上游通道</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/models">
          <el-icon><Box /></el-icon><span>可用模型</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/announcements">
          <el-icon><Bell /></el-icon><span>系统公告</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/users">
          <el-icon><UserFilled /></el-icon><span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/rate-config">
          <el-icon><Setting /></el-icon><span>速率配置</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <!-- 桌面端侧边栏 -->
    <el-aside width="240px" class="sidebar" v-if="!isMobile">
      <div class="brand">
        <BrandLogo size="md" />
        <span class="brand-text">AGNES2API</span>
        <span class="brand-version">v2.1</span>
      </div>
      <div class="nav-sep"></div>
      <el-menu :default-active="activeRoute" class="nav-menu" @select="handleNavSelect">
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon><span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/keys">
          <el-icon><Key /></el-icon><span>授权密钥</span>
        </el-menu-item>
        <el-menu-item index="/upstream">
          <el-icon><Connection /></el-icon><span>上游通道</span>
        </el-menu-item>
        <div class="nav-group-label" v-if="authStore.role === 'admin'">系统管理</div>
        <el-menu-item v-if="authStore.role === 'admin'" index="/models">
          <el-icon><Box /></el-icon><span>可用模型</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/announcements">
          <el-icon><Bell /></el-icon><span>系统公告</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/users">
          <el-icon><UserFilled /></el-icon><span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/rate-config">
          <el-icon><Setting /></el-icon><span>速率配置</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <span class="footer-version">v2.1</span>
      </div>
    </el-aside>

    <div class="main-content">
      <el-header class="header" v-if="!isMobile">
        <div class="header-left">
          <h2 class="page-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <span class="user-info">
            <span class="user-role-badge">{{ authStore.role === 'admin' ? '管理员' : '普通用户' }}</span>
            <span class="user-name">{{ authStore.username }}</span>
          </span>
          <el-button text @click="announcementStore.openForReview()">
            <el-icon class="el-icon--left"><Bell /></el-icon>公告
          </el-button>
          <el-button text @click="pwdStore.showModal = true">
            <el-icon class="el-icon--left"><Lock /></el-icon>修改密码
          </el-button>
          <el-button type="danger" text @click="authStore.logout()">
            <el-icon class="el-icon--left"><SwitchButton /></el-icon>退出登录
          </el-button>
        </div>
      </el-header>

      <div class="content-body">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="pwdStore.showModal" title="修改密码" width="400px">
      <el-form @submit.prevent="pwdStore.handleChangePassword" label-position="top">
        <el-form-item label="原密码">
          <el-input v-model="pwdStore.form.old" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdStore.form.new" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdStore.form.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdStore.showModal = false">取消</el-button>
        <el-button type="primary" @click="pwdStore.handleChangePassword">保存修改</el-button>
      </template>
    </el-dialog>

    <AnnouncementDialog />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePwdStore } from '@/stores/pwd'
import { useAnnouncementStore } from '@/stores/announcement'
import AnnouncementDialog from '@/components/AnnouncementDialog.vue'
import BrandLogo from '@/components/BrandLogo.vue'
import { DataLine, Key, Connection, Lock, SwitchButton, UserFilled, Setting, Bell, Box } from '@element-plus/icons-vue'
import { useDevice } from '@/composables/useDevice'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const pwdStore = usePwdStore()
const announcementStore = useAnnouncementStore()
const { isMobile } = useDevice()

const activeRoute = computed(() => route.path)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/dashboard': '全局模型成功率看板',
    '/keys': '授权密钥管理',
    '/upstream': '上游通道配置',
    '/models': '可用模型配置',
    '/announcements': '系统公告管理',
    '/users': '用户管理',
    '/rate-config': '速率配置',
  }
  return titles[route.path] || ''
})

function handleNavSelect(index: string) {
  router.push(index)
}

const sidebarVisible = ref(false)

onMounted(async () => {
  if (!authStore.justLoggedIn) return
  authStore.justLoggedIn = false
  await announcementStore.loadDismissed()
  await announcementStore.fetchActive()
  announcementStore.displayAll = false
  if (announcementStore.visibleAnnouncements.length > 0) {
    announcementStore.showDialog = true
  }
})
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
  background: var(--el-bg-color-page);
}

/* ============================================================
   SIDEBAR
   ============================================================ */
.sidebar {
  width: 240px !important;
  background: var(--bg-primary) !important;
  border-right: 1px solid var(--border-subtle) !important;
  display: flex;
  flex-direction: column;
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
}

.brand {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.brand-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.brand-version {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}

.nav-sep {
  height: 1px;
  background: var(--border-subtle);
  margin: 0 20px;
}

.nav-menu {
  flex: 1;
  background: transparent !important;
  border: none;
  padding: 8px 10px;
}

.nav-group-label {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  padding: 16px 12px 6px;
}

.nav-menu .el-menu-item {
  color: var(--text-secondary);
  height: 40px;
  line-height: 40px;
  border-radius: 6px;
  margin-bottom: 2px;
  border-left: 2px solid transparent;
  transition: all 0.15s ease !important;
}

.nav-menu .el-menu-item:hover {
  background: var(--bg-elevated) !important;
  color: var(--text-primary) !important;
}

.nav-menu .el-menu-item.is-active {
  background: var(--accent-dim) !important;
  color: var(--accent-light) !important;
  font-weight: 500;
}

.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-subtle);
}

.footer-version {
  font-size: 11px;
  color: var(--text-muted);
}

/* ============================================================
   MAIN CONTENT
   ============================================================ */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--el-bg-color-page);
}

.header {
  height: 56px;
  background: var(--bg-primary) !important;
  border-bottom: 1px solid var(--border-subtle) !important;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-right: 8px;
}

.user-role-badge {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--accent-dim);
  color: var(--accent-light);
}

.user-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.content-body {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
}

/* ============================================================
   MOBILE
   ============================================================ */
.mobile-header {
  height: 52px;
  background: var(--bg-primary) !important;
  border-bottom: 1px solid var(--border-subtle) !important;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.mobile-menu-btn {
  color: var(--text-secondary) !important;
}

.mobile-page-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 55%;
}

.mobile-header-actions {
  display: flex;
  gap: 4px;
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 99;
}

:deep(.mobile-sidebar-drawer .el-drawer__header) { display: none; }
:deep(.mobile-sidebar-drawer .el-drawer__body) { padding: 0; background: var(--bg-primary) !important; }

@media (max-width: 768px) {
  .app-layout { flex-direction: column; }
  .main-content { width: 100%; }
  .content-body { padding: 12px 16px; }
  .mobile-header { width: 100%; flex-shrink: 0; }
}

@media (max-width: 480px) {
  .content-body { padding: 10px 12px; }
  .mobile-page-title { flex: 1; max-width: none; min-width: 0; margin: 0 8px; }
}
</style>
