import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/services/http'
import { fetchUserDashboardStats } from '@/services/api'
import { useAuthStore } from './auth'
import type { GlobalModelStats, TimelineEntry } from '@/types/api'

function makeAuthStore() { return useAuthStore() }

export const useDashboardStore = defineStore('dashboard', () => {
  const userStats = ref<GlobalModelStats>({
    text: { total: 0, success: 0, failure: 0, success_rate: 0 },
    image: { total: 0, success: 0, failure: 0, success_rate: 0 },
    video: { total: 0, success: 0, failure: 0, success_rate: 0 },
    summary: { total: 0, success: 0, failure: 0, success_rate: 0 },
  })
  const timelineData = ref<TimelineEntry[]>([])
  const autoRefresh = ref(false)

  async function fetchDashboardStats() {
    const authStore = makeAuthStore()
    if (!authStore.isLoggedIn) return
    const stats = await fetchUserDashboardStats()
    userStats.value = stats
  }

  async function refreshDashboard() {
    await Promise.all([
      fetchDashboardStats(),
      fetchTimeline(30),
    ])
  }

  async function fetchTimeline(minutes: number = 30) {
    try {
      const data = await http.get<TimelineEntry[]>('/dashboard/timeline', { params: { minutes } })
      timelineData.value = data
    } catch (e) {
      console.error('Failed to fetch timeline:', e)
      timelineData.value = []
    }
  }

  return {
    userStats,
    timelineData,
    autoRefresh,
    fetchDashboardStats,
    refreshDashboard,
    fetchTimeline,
  }
})
