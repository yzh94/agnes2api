import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/services/http'
import { fetchUpstreamStats, fetchUserDashboardStats } from '@/services/api'
import { useAuthStore } from './auth'
import type { UpstreamStat, GlobalModelStats } from '@/types/api'

export const useDashboardStore = defineStore('dashboard', () => {
  const upstreamStats = ref<UpstreamStat[]>([])
  const keyPoolStats = ref<any[]>([])
  const globalStats = ref<GlobalModelStats>({
    text: { total: 0, success: 0, failure: 0, success_rate: 0 },
    image: { total: 0, success: 0, failure: 0, success_rate: 0 },
    video: { total: 0, success: 0, failure: 0, success_rate: 0 },
    summary: { total: 0, success: 0, failure: 0, success_rate: 0 },
  })
  const userStats = ref<GlobalModelStats>({
    text: { total: 0, success: 0, failure: 0, success_rate: 0 },
    image: { total: 0, success: 0, failure: 0, success_rate: 0 },
    video: { total: 0, success: 0, failure: 0, success_rate: 0 },
    summary: { total: 0, success: 0, failure: 0, success_rate: 0 },
  })
  const timelineData = ref<any[]>([])
  const isLoading = ref(false)
  const autoRefresh = ref(false)
  const hasData = ref(false)

  // 优先展示真实统计数据，若无数据则回退到 Key Pool 状态
  const statsData = computed(() => {
    return hasData.value ? upstreamStats.value : keyPoolStats.value
  })

  const mapModelName = (model: string) => {
    const map: Record<string, string> = {
      text: 'agnes-2.0-flash',
      image: 'agnes-image-2.1-flash',
      video: 'agnes-video-v2.0',
    }
    return map[model] || model
  }

  const getSuccessColor = (rate: number) => {
    if (rate > 90) return '#10b981'
    if (rate > 60) return '#f59e0b'
    return '#ef4444'
  }

  async function fetchStats() {
    const authStore = useAuthStore()
    if (!authStore.isLoggedIn) return

    isLoading.value = true
    try {
      // 尝试获取真实统计数据
      const stats = await fetchUpstreamStats()
      if (stats && stats.length > 0) {
        upstreamStats.value = stats
        hasData.value = true
        keyPoolStats.value = []
      } else {
        // 回退到 Key Pool 状态
        hasData.value = false
        await fetchKeyPoolStatus()
      }
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDashboardStats() {
    const authStore = useAuthStore()
    if (!authStore.isLoggedIn) return

    isLoading.value = true
    try {
      // 调用 GET /api/manage/dashboard/me 获取当前用户当日统计
      const stats = await fetchUserDashboardStats()
      userStats.value = stats
    } finally {
      isLoading.value = false
    }
  }

  async function refreshDashboard() {
    await Promise.all([
      fetchDashboardStats(),
      fetchTimeline(24),
    ])
  }

  async function fetchTimeline(hours: number = 24) {
    try {
      const data = await http.get('/dashboard/timeline', { params: { hours } })
      timelineData.value = data
    } catch (e) {
      console.error('Failed to fetch timeline:', e)
      timelineData.value = []
    }
  }

  async function fetchKeyPoolStatus() {
    try {
      // http.ts 已经将 baseURL 设置为了 '/api/manage'
      // 这里的正确 API 是 GET /api/keys/pool
      const response = await fetch('/api/keys/pool', {
        headers: {
          'Authorization': `Bearer ${useAuthStore().token}`
        }
      }).then(res => res.json())

      if (response && response.keys) {
        keyPoolStats.value = response.keys.map((k: any) => ({
          name: k.key_prefix,
          masked_key: k.key_prefix,
          status: k.status,
          total: k.total_success + k.total_failure,
          success: k.total_success,
          failure: k.total_failure,
          success_rate: 0,
          text: { total: 0, success: 0, failure: 0, success_rate: 0 },
          image: { total: 0, success: 0, failure: 0, success_rate: 0 },
          video: { total: 0, success: 0, failure: 0, success_rate: 0 },
        }))
      }
    } catch (e) {
      console.error('Failed to fetch key pool status:', e)
      keyPoolStats.value = []
    }
  }

  function toggleAutoRefresh() {
    autoRefresh.value = !autoRefresh.value
  }

  return {
    upstreamStats,
    keyPoolStats,
    globalStats,
    userStats,
    timelineData,
    isLoading,
    hasData,
    autoRefresh,
    statsData,
    mapModelName,
    getSuccessColor,
    fetchStats,
    fetchDashboardStats,
    refreshDashboard,
    fetchTimeline,
    toggleAutoRefresh,
  }
})
