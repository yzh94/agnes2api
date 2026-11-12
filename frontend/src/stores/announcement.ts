import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchAnnouncements } from '@/services/api'
import { safeParseJSON } from '@/utils/storage'
import type { AnnouncementItem } from '@/types/api'

export const useAnnouncementStore = defineStore('announcement', () => {
  const allActive = ref<AnnouncementItem[]>([])
  const dismissedIds = ref<Set<number>>(new Set(safeParseJSON<number[]>('dismissed_announcements', [])))
  const showDialog = ref(false)
  const displayAll = ref(false)

  const visibleAnnouncements = computed(() =>
    displayAll.value
      ? allActive.value
      : allActive.value.filter((a) => !dismissedIds.value.has(a.id))
  )

  async function loadDismissed() {
    dismissedIds.value = new Set(safeParseJSON<number[]>('dismissed_announcements', []))
  }

  async function fetchActive() {
    try {
      allActive.value = await fetchAnnouncements()
    } catch {
      allActive.value = []
    }
  }

  function dismiss(id: number) {
    dismissedIds.value.add(id)
    localStorage.setItem('dismissed_announcements', JSON.stringify([...dismissedIds.value]))
  }

  function dismissAll() {
    allActive.value.forEach((a) => dismissedIds.value.add(a.id))
    localStorage.setItem('dismissed_announcements', JSON.stringify([...dismissedIds.value]))
  }

  async function openForReview() {
    displayAll.value = true
    await fetchActive()
    showDialog.value = true
  }

  return {
    allActive,
    dismissedIds,
    showDialog,
    displayAll,
    visibleAnnouncements,
    loadDismissed,
    fetchActive,
    dismiss,
    dismissAll,
    openForReview,
  }
})
