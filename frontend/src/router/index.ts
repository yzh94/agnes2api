import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LayoutView from '@/views/LayoutView.vue'

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
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.path !== '/login') {
    const authStore = useAuthStore()
    if (!authStore.isLoggedIn) {
      return '/login'
    }
  }
})

export default router
