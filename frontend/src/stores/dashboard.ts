import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/services/http'

export const useDashboardStore = defineStore('dashboard', () => {
  const timelineData = ref<any[]>([])
  const autoRefresh = ref(false)

  async function refreshDashboard() {
    await fetchTimeline(24)
  }

  async function fetchTimeline(hours: number = 24) {
    try {
      const data = (await http.get('/dashboard/timeline', { params: { hours } })) as any[]
      timelineData.value = data
    } catch (e) {
      console.error('Failed to fetch timeline:', e)
      timelineData.value = []
    }
  }

  return {
    timelineData,
    autoRefresh,
    refreshDashboard,
    fetchTimeline,
  }
})
