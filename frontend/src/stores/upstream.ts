import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getUpstreamKeys,
  createUpstreamKey,
  updateUpstreamWeight,
  toggleUpstreamStatus,
  deleteUpstreamKey,
  validateUpstreamKey,
  validateAllUpstreamKeys,
  cleanDisabledKeys,
} from '@/services/api'
import { useAuthStore } from './auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UpstreamKeyResponse } from '@/types/api'

export const useUpstreamStore = defineStore('upstream', () => {
  const upstreamKeys = ref<UpstreamKeyResponse[]>([])
  const isLoading = ref(false)
  const authStore = useAuthStore()

  async function fetchUpstreamKeys() {
    if (!authStore.isLoggedIn) return
    isLoading.value = true
    try {
      upstreamKeys.value = await getUpstreamKeys()
    } finally {
      isLoading.value = false
    }
  }

  async function handleCreateKey(name: string, key: string) {
    await createUpstreamKey(name, key)
    await fetchUpstreamKeys()
    ElMessage.success('渠道创建成功')
  }

  async function handleUpdateWeight(id: number, weight: number) {
    await updateUpstreamWeight(id, weight)
    await fetchUpstreamKeys()
    ElMessage.success('权重更新成功')
  }

  async function handleToggleStatus(id: number, currentStatus: string) {
    const newStatus = currentStatus === 'active' ? 'disabled' : 'active'
    await toggleUpstreamStatus(id, newStatus)
    await fetchUpstreamKeys()
  }

  async function handleDeleteKey(id: number) {
    await deleteUpstreamKey(id)
    await fetchUpstreamKeys()
    ElMessage.success('渠道删除成功')
  }

  async function handleValidateKey(id: number) {
    try {
      const res = await validateUpstreamKey(id)
      if (res.validated) {
        ElMessage.success('检验通过')
      } else {
        ElMessage.warning(res.message || '检验失败，Key 已禁用')
      }
      await fetchUpstreamKeys()
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '检验失败')
    }
  }

  async function handleValidateAll(concurrency: number) {
    try {
      const res = await validateAllUpstreamKeys(concurrency)
      const { summary, results } = res
      let msg = `检验完成：总计 ${summary.total} | 通过 ${summary.success} | 失败 ${summary.failed}`
      ElMessageBox.alert(
        `<div style="margin-bottom:12px;">${msg}</div>
         <table style="width:100%;border-collapse:collapse;font-size:13px;">
           <tr><th style="text-align:left;padding:4px;">通道</th><th style="padding:4px;">前缀</th><th style="padding:4px;">结果</th><th style="padding:4px;">详情</th></tr>
           ${results.map(r => `<tr>
             <td style="padding:4px;">${r.name}</td>
             <td style="padding:4px;font-family:monospace;">${r.masked_key}</td>
             <td style="padding:4px;color:${r.success ? '#67c23a' : '#f56c6c'};">${r.success ? '✅ 通过' : '❌ 失败'}</td>
             <td style="padding:4px;color:#909399;">${r.message}</td>
           </tr>`).join('')}
         </table>`,
        '全量检验结果',
        { dangerouslyUseHTMLString: true, confirmButtonText: '关闭' }
      )
      await fetchUpstreamKeys()
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '全量检验失败')
    }
  }

  async function handleCleanDisabled() {
    try {
      const res = await cleanDisabledKeys()
      ElMessage.success(res.message || '清理完成')
      await fetchUpstreamKeys()
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '清理失败')
    }
  }

  return {
    upstreamKeys,
    isLoading,
    fetchUpstreamKeys,
    handleCreateKey,
    handleUpdateWeight,
    handleToggleStatus,
    handleDeleteKey,
    handleValidateKey,
    handleValidateAll,
    handleCleanDisabled,
  }
})