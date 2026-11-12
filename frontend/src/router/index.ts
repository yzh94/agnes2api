import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LayoutView from '@/views/LayoutView.vue'

let cachedAuthStore: ReturnType<typeof useAuthStore> | null = null

function getAuthStore() {
  if (!cachedAuthStore) {
    cachedAuthStore = useAuthStore()
  }
  return cachedAuthStore
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/',
      component: LayoutView,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },
        {
          path: 'keys',
          name: 'Keys',
          component: () => import('@/views/KeysView.vue'),
        },
        {
          path: 'upstream',
          name: 'Upstream',
          component: () => import('@/views/UpstreamView.vue'),
        },
        {
          path: 'models',
          name: 'Models',
          component: () => import('@/views/ModelsView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'announcements',
          name: 'Announcements',
          component: () => import('@/views/AnnouncementsView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'users',
          name: 'Users',
          component: () => import('@/views/UserManagementView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'rate-config',
          name: 'RateConfig',
          component: () => import('@/views/RateConfigView.vue'),
          meta: { requiresAdmin: true },
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  // 处理 Discord OAuth 回调：从 URL 提取 token 并写入 localStorage
  if (to.query.token) {
    const token = Array.isArray(to.query.token) ? to.query.token[0] : to.query.token
    if (typeof token === 'string' && token.length > 0) {
      localStorage.setItem('agnes2api_token', token)
      localStorage.setItem('agnes2api_role', 'user')
      return to.fullPath.replace(/\?token=[^&]*/g, '')
    }
  }
  if (to.path !== '/login') {
    const authStore = getAuthStore()
    if (!authStore.isLoggedIn) {
      return '/login'
    }
    if (to.meta.requiresAdmin && authStore.role !== 'admin') {
      return '/dashboard'
    }
  }
})

export default router
