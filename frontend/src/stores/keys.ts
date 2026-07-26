import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getKeys, createKey, resetKey, toggleKeyStatus, deleteKey } from '@/services/api'
import { useAuthStore } from './auth'
import { ElMessage } from 'element-plus'
import type { KeyResponse } from '@/types/api'

export const useKeysStore = defineStore('keys', () => {
  const keys = ref<KeyResponse[]>([])
  const isLoading = ref(false)
  const authStore = useAuthStore()

  async function fetchKeys() {
    if (!authStore.isLoggedIn) return
    isLoading.value = true
    try {
      keys.value = await getKeys()
    } finally {
      isLoading.value = false
    }
  }

  async function handleCreateKey(name: string) {
    await createKey(name)
    await fetchKeys()
    ElMessage.success('Key 创建成功')
  }

  async function handleResetKey(_id: number) {
    try {
      const res = await resetKey()
      ElMessage.success('Key 重置成功，新密钥: ' + res.key)
      await fetchKeys()
    } catch (err: any) {
      ElMessage.error(err.response?.data?.detail || '重置失败')
    }
  }

  async function handleToggleStatus(id: number, currentStatus: string) {
    const newStatus = currentStatus === 'active' ? 'disabled' : 'active'
    await toggleKeyStatus(id, newStatus)
    await fetchKeys()
  }

  async function handleDeleteKey(id: number) {
    await deleteKey(id)
    await fetchKeys()
    ElMessage.success('Key 删除成功')
  }

  return {
    keys,
    isLoading,
    fetchKeys,
    handleCreateKey,
    handleResetKey,
    handleToggleStatus,
    handleDeleteKey,
  }
})