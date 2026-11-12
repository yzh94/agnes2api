import { defineStore } from 'pinia'
import { h, ref } from 'vue'
import {
  getUpstreamKeys,
  createUpstreamKey,
  toggleUpstreamStatus,
  deleteUpstreamKey,
  validateUpstreamKey,
  validateAllUpstreamKeys,
  getValidateAllStatus,
  cleanDisabledKeys,
} from '@/services/api'
import { useAuthStore } from './auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UpstreamKeyResponse, UpstreamKeySummary } from '@/types/api'

function makeAuthStore() { return useAuthStore() }

export const useUpstreamStore = defineStore('upstream', () => {
  const upstreamKeys = ref<UpstreamKeyResponse[]>([])
  const isLoading = ref(false)
  const currentPage = ref(1)
  const pageSize = ref(10)
  const total = ref(0)
  const summary = ref<UpstreamKeySummary>({ total: 0, active: 0, disabled: 0 })
  const lastValidationAt = ref<string | null>(null)
  const validatingAll = ref(false)
  const validateProgress = ref<{ done: number; total: number }>({ done: 0, total: 0 })
  const searchKeyword = ref('')
  const statusFilter = ref('')
  // 实时刷新轮询句柄（Redis 状态以秒级变化，前端轻量轮询保证展示接近实时）
  let pollTimer: ReturnType<typeof setInterval> | null = null
  const POLL_INTERVAL_MS = 15000

  async function fetchUpstreamKeys(retryPreviousPage = true, silent = false) {
    const authStore = makeAuthStore()
    if (!authStore.isLoggedIn) return
    if (!silent) isLoading.value = true
    try {
      const res = await getUpstreamKeys(currentPage.value, pageSize.value, searchKeyword.value, statusFilter.value)
      upstreamKeys.value = res.items
      total.value = res.total
      summary.value = res.summary
      lastValidationAt.value = res.last_validation_at

      if (retryPreviousPage && res.items.length === 0 && res.total > 0 && currentPage.value > 1) {
        currentPage.value -= 1
        await fetchUpstreamKeys(false, silent)
      }
    } finally {
      if (!silent) isLoading.value = false
    }
  }

  function setSearchKeyword(kw: string) {
    searchKeyword.value = kw
    currentPage.value = 1
    fetchUpstreamKeys()
  }

  function setStatusFilter(s: string) {
    statusFilter.value = s
    currentPage.value = 1
    fetchUpstreamKeys()
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(() => {
      // 后台静默刷新，不触发 loading 态；失败不影响现有展示
      fetchUpstreamKeys(false, true).catch(() => {})
    }, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function setPage(page: number) {
    currentPage.value = page
    fetchUpstreamKeys()
  }

  function setPageSize(size: number) {
    pageSize.value = size
    currentPage.value = 1
    fetchUpstreamKeys()
  }

  async function handleCreateKey(name: string, key: string) {
    await createUpstreamKey(name, key)
    await fetchUpstreamKeys()
    ElMessage.success('渠道创建成功')
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
    const res = await validateUpstreamKey(id)
    if (res.validated) {
      ElMessage.success('检验通过')
    } else {
      ElMessage.warning(res.message || '检验失败，Key 已禁用')
    }
    await fetchUpstreamKeys()
  }

  function showValidateResult(state: any) {
    const results = Array.isArray(state.results) ? state.results : []
    const lines = results.map((r: any) =>
      `${r.name} | ${r.masked_key} | ${r.success ? '通过' : '失败'} | ${r.message}`
    ).join('\n')
    const msg = state.status === 'success'
      ? `检验完成：总计 ${state.total} | 通过 ${state.success} | 失败 ${state.failed}\n\n${lines}`
      : `失败 Key 检验中断：${state.message || '未知错误'}`
    ElMessageBox.alert(msg, '失败 Key 检验结果', {
      confirmButtonText: '关闭',
      message: h('pre', { style: 'white-space: pre-line; margin: 0; font-size: 12px; line-height: 1.6;' }, msg),
    })
  }

  // 失败 Key 检验已异步任务化：POST 立即返回，后台执行，前端轮询进度，不受 30s 超时限制
  async function pollValidationState() {
    if (validatingAll.value) return  // 已在轮询中，避免重复循环
    validatingAll.value = true
    try {
      // 最多轮询 20 分钟（600 × 2s），正常几十秒内结束
      for (let i = 0; i < 600; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const st = await getValidateAllStatus()
        validateProgress.value = { done: st.done ?? 0, total: st.total ?? 0 }
        if (st.status !== 'running') {
          showValidateResult(st)
          break
        }
      }
    } catch {
      ElMessage.error('进度查询失败，请稍后刷新查看结果')
    } finally {
      validatingAll.value = false
      await fetchUpstreamKeys()
    }
  }

  async function handleValidateAll(concurrency: number) {
    if (validatingAll.value) return
    const res = await validateAllUpstreamKeys(concurrency)
    if (res.status === 'already_running') {
      ElMessage.info('失败 Key 检验正在进行中，已为您接上进度')
    }
    validateProgress.value = { done: res.state?.done ?? 0, total: res.state?.total ?? 0 }
    await pollValidationState()
  }

  // 页面挂载时同步检验状态：定时任务或其他管理员触发的检验进行中时，接管进度展示
  async function syncValidationState() {
    if (validatingAll.value) return
    try {
      const st = await getValidateAllStatus()
      if (st.status === 'running') {
        validateProgress.value = { done: st.done ?? 0, total: st.total ?? 0 }
        ElMessage.info('检测到有失败 Key 检验正在进行')
        pollValidationState()
      }
    } catch {
      // 状态查询失败不影响页面正常使用
    }
  }

  async function handleCleanDisabled() {
    const res = await cleanDisabledKeys()
    ElMessage.success(res.message || '清理完成')
    await fetchUpstreamKeys()
  }

  return {
    upstreamKeys,
    isLoading,
    currentPage,
    pageSize,
    total,
    summary,
    lastValidationAt,
    validatingAll,
    validateProgress,
    searchKeyword,
    statusFilter,
    fetchUpstreamKeys,
    setSearchKeyword,
    setStatusFilter,
    startPolling,
    stopPolling,
    setPage,
    setPageSize,
    handleCreateKey,
    handleToggleStatus,
    handleDeleteKey,
    handleValidateKey,
    handleValidateAll,
    syncValidationState,
    handleCleanDisabled,
  }
})
