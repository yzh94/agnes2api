<template>
  <div class="dashboard">
    <!-- 右上角刷新控制 -->
    <div class="dashboard-header">
      <div class="header-actions">
        <el-switch
          v-model="dashboardStore.autoRefresh"
          active-text="自动刷新"
        />
        <el-button @click="refreshAll" :loading="refreshing">手动刷新</el-button>
      </div>
    </div>

    <!-- 用户当日模型成功率卡片 -->
    <div class="kpi-container">
      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon blue"><el-icon><ChatDotRound /></el-icon></div>
          <div class="kpi-label">文本模型</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.text.success_rate) }">
          {{ stats.text.success_rate }}%
        </div>
        <div class="kpi-detail">
          总量 {{ stats.text.total }} · 成功 {{ stats.text.success }} · 失败 {{ stats.text.failure }}
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon green"><el-icon><Picture /></el-icon></div>
          <div class="kpi-label">图像模型</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.image.success_rate) }">
          {{ stats.image.success_rate }}%
        </div>
        <div class="kpi-detail">
          总量 {{ stats.image.total }} · 成功 {{ stats.image.success }} · 失败 {{ stats.image.failure }}
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon purple"><el-icon><VideoCamera /></el-icon></div>
          <div class="kpi-label">视频模型</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.video.success_rate) }">
          {{ stats.video.success_rate }}%
        </div>
        <div class="kpi-detail">
          总量 {{ stats.video.total }} · 成功 {{ stats.video.success }} · 失败 {{ stats.video.failure }}
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon orange"><el-icon><Odometer /></el-icon></div>
          <div class="kpi-label">用户当日总计</div>
        </div>
        <div class="kpi-value">{{ stats.summary.total.toLocaleString() }}</div>
        <div class="kpi-detail">
          成功率 {{ stats.summary.success_rate }}%
        </div>
      </el-card>
    </div>

    <!-- 时间序列折线图 - 全局视角 -->
    <el-card shadow="never" class="timeline-card">
      <template #header>
        <span class="card-title">近24小时全局模型成功率趋势</span>
      </template>
      <div ref="chartRef" class="chart-container"></div>
    </el-card>

    <!-- 管理员看板：Key 池模型统计（全 Key 聚合） -->
    <el-card v-if="authStore.role === 'admin'" shadow="never" class="admin-panel">
      <template #header>
        <span class="card-title">Key 池模型调用统计（全 Key 聚合 · 北京时间 0 点重置）</span>
      </template>
      <div v-if="!adminDataLoaded && adminLoading" class="admin-loading">加载中...</div>
      <div v-else class="kpi-container">
        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon blue"><el-icon><ChatDotRound /></el-icon></div>
            <div class="kpi-label">文本模型</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.text.success_rate) }">
            {{ adminKeyPool.text.success_rate }}%
          </div>
          <div class="kpi-detail">
            总量 {{ adminKeyPool.text.total }} · 成功 {{ adminKeyPool.text.success }} · 失败 {{ adminKeyPool.text.failure }}
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon green"><el-icon><Picture /></el-icon></div>
            <div class="kpi-label">图像模型</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.image.success_rate) }">
            {{ adminKeyPool.image.success_rate }}%
          </div>
          <div class="kpi-detail">
            总量 {{ adminKeyPool.image.total }} · 成功 {{ adminKeyPool.image.success }} · 失败 {{ adminKeyPool.image.failure }}
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon purple"><el-icon><VideoCamera /></el-icon></div>
            <div class="kpi-label">视频模型</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.video.success_rate) }">
            {{ adminKeyPool.video.success_rate }}%
          </div>
          <div class="kpi-detail">
            总量 {{ adminKeyPool.video.total }} · 成功 {{ adminKeyPool.video.success }} · 失败 {{ adminKeyPool.video.failure }}
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon orange"><el-icon><Odometer /></el-icon></div>
            <div class="kpi-label">全 Key 总计</div>
          </div>
          <div class="kpi-value">{{ adminKeyPool.summary.total.toLocaleString() }}</div>
          <div class="kpi-detail">
            成功率 {{ adminKeyPool.summary.success_rate }}%
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 管理员看板：用户请求次数排名 -->
    <el-card v-if="authStore.role === 'admin'" shadow="never" class="admin-panel">
      <template #header>
        <span class="card-title">用户请求次数排名（当日 · 北京时间 0 点重置）</span>
      </template>
      <div v-if="!adminDataLoaded && adminLoading" class="admin-loading">加载中...</div>
      <div class="user-rank-list">
        <div v-for="(item, idx) in adminUserRanking" :key="item.user_id" class="rank-row" :class="{ 'rank-top': globalIdx(idx) < 3 }">
          <div class="rank-index">
            <el-tag v-if="globalIdx(idx) === 0" type="warning" size="small" effect="dark">🥇</el-tag>
            <el-tag v-else-if="globalIdx(idx) === 1" type="info" size="small" effect="plain">🥈</el-tag>
            <el-tag v-else-if="globalIdx(idx) === 2" type="danger" size="small" effect="plain">🥉</el-tag>
            <span v-else>{{ globalIdx(idx) + 1 }}</span>
          </div>
          <div class="rank-info">
            <div class="rank-main">
              <span class="rank-name">{{ item.username }}</span>
              <span class="rank-total-inline">总请求 {{ item.total_requests.toLocaleString() }} 次</span>
            </div>
            <div class="rank-model-grid">
              <div class="rank-model-item">
                <span class="rank-model-label">文本</span>
                <span class="rank-model-count">{{ item.text_requests }} 次</span>
                <span class="rank-model-rate" :style="{ color: getSuccessColor(item.text_success_rate) }">{{ item.text_success_rate }}%</span>
              </div>
              <div class="rank-model-item">
                <span class="rank-model-label">图像</span>
                <span class="rank-model-count">{{ item.image_requests }} 次</span>
                <span class="rank-model-rate" :style="{ color: getSuccessColor(item.image_success_rate) }">{{ item.image_success_rate }}%</span>
              </div>
              <div class="rank-model-item">
                <span class="rank-model-label">视频</span>
                <span class="rank-model-count">{{ item.video_requests }} 次</span>
                <span class="rank-model-rate" :style="{ color: getSuccessColor(item.video_success_rate) }">{{ item.video_success_rate }}%</span>
              </div>
            </div>
          </div>
          <div class="rank-stats">
            <span class="rank-total">{{ item.total_requests.toLocaleString() }} 次</span>
            <span class="rank-rate" :style="{ color: getSuccessColor(item.success_rate) }">总成功率 {{ item.success_rate }}%</span>
          </div>
        </div>
        <div v-if="!adminLoading && adminUserRanking.length === 0" class="empty-tip">暂无用户请求数据</div>
      </div>
      <div v-if="adminPagination && adminPagination.total_pages > 1" class="admin-pagination-wrap">
        <el-pagination
          v-model:current-page="adminPage"
          :page-size="adminPageSize"
          :total="adminPagination.total"
          layout="total, prev, pager, next, jumper"
          background
          @current-change="handleAdminPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref, onUnmounted, watch, nextTick } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import { useAuthStore } from '@/stores/auth'
import { ChatDotRound, Picture, VideoCamera, Odometer } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { fetchAdminDashboard } from '@/services/api'
import type { GlobalModelStats, AdminUserRanking, AdminPagination } from '@/types/api'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()
const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

const stats = computed(() => dashboardStore.userStats)

// 管理员看板数据
const EMPTY_MODEL_STATS: GlobalModelStats = {
  text: { total: 0, success: 0, failure: 0, success_rate: 0 },
  image: { total: 0, success: 0, failure: 0, success_rate: 0 },
  video: { total: 0, success: 0, failure: 0, success_rate: 0 },
  summary: { total: 0, success: 0, failure: 0, success_rate: 0 },
}
const adminKeyPool = ref<GlobalModelStats>({ ...EMPTY_MODEL_STATS })
const adminUserRanking = ref<AdminUserRanking[]>([])
const adminLoading = ref(false)
const adminDataLoaded = ref(false)
const adminPage = ref(1)
const adminPageSize = ref(10)
const adminPagination = ref<AdminPagination | null>(null)

function getSuccessColor(rate: number) {
  if (rate > 90) return '#10b981'
  if (rate > 60) return '#f59e0b'
  return '#ef4444'
}

function globalIdx(localIdx: number) {
  return (adminPage.value - 1) * adminPageSize.value + localIdx
}

async function loadAdminData() {
  if (authStore.role !== 'admin') return
  adminLoading.value = true
  // 不重置 adminDataLoaded：刷新时保留旧数据避免面板闪烁，首次加载仍正常展示加载态
  try {
    const res = await fetchAdminDashboard(adminPage.value, adminPageSize.value)
    adminKeyPool.value = res.key_pool ?? EMPTY_MODEL_STATS
    adminUserRanking.value = res.user_ranking || []
    adminPagination.value = res.pagination || null
  } catch {
    // http 拦截器已统一提示错误
  } finally {
    adminLoading.value = false
    adminDataLoaded.value = true
  }
}

function handleAdminPageChange(page: number) {
  adminPage.value = page
  loadAdminData()
}

// 刷新看板全部数据：用户 KPI + 时间序列 + 管理员 Key 池/排名
const refreshing = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

async function refreshAll() {
  refreshing.value = true
  try {
    await Promise.all([
      dashboardStore.refreshDashboard(),
      loadAdminData(),
    ])
  } finally {
    refreshing.value = false
  }
}

// 自动刷新：每 10s 刷新看板全部数据（含管理员数据）
watch(() => dashboardStore.autoRefresh, (val) => {
  if (val) {
    refreshTimer = setInterval(refreshAll, 10000)
  } else if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

function renderChart() {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const data = dashboardStore.timelineData
  if (!data || data.length === 0) {
    chartInstance.setOption({
      title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#999' } },
      xAxis: { type: 'category', data: [] },
      yAxis: { type: 'value', name: '成功率 (%)', min: 0, max: 100 },
      series: [],
    }, true)
    return
  }

  const labels = data.map((d: any) => {
    const parts = d.timestamp.split('T')
    return parts[0].slice(5) + ' ' + parts[1].slice(0, 5)
  })
  const textRates = data.map((d: any) => +(d.text?.success_rate ?? 0).toFixed(2))
  const imageRates = data.map((d: any) => +(d.image?.success_rate ?? 0).toFixed(2))
  const videoRates = data.map((d: any) => +(d.video?.success_rate ?? 0).toFixed(2))

  chartInstance.setOption({
    title: { text: '' },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      formatter: (params: any) => {
        let html = params[0]?.axisValue + '<br/>'
        params.forEach((p: any) => {
          html += `${p.marker} ${p.seriesName}: ${p.value}%<br/>`
        })
        return html
      },
    },
    legend: { data: ['文本', '图像', '视频'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisTick: { alignWithLabel: true },
    },
    yAxis: {
      type: 'value',
      name: '成功率 (%)',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' },
    },
    series: [
      {
        name: '文本',
        type: 'line',
        smooth: true,
        data: textRates,
        itemStyle: { color: '#3b82f6' },
        areaStyle: { color: 'rgba(59,130,246,0.1)' },
      },
      {
        name: '图像',
        type: 'line',
        smooth: true,
        data: imageRates,
        itemStyle: { color: '#10b981' },
        areaStyle: { color: 'rgba(16,185,129,0.1)' },
      },
      {
        name: '视频',
        type: 'line',
        smooth: true,
        data: videoRates,
        itemStyle: { color: '#8b5cf6' },
        areaStyle: { color: 'rgba(139,92,246,0.1)' },
      },
    ],
  }, true)
}

// 监听 timelineData 变化，自动重绘
watch(() => dashboardStore.timelineData, () => {
  nextTick(() => renderChart())
}, { deep: true })

// 窗口大小变化时重设图表尺寸
function handleResize() {
  chartInstance?.resize()
}

onMounted(async () => {
  await refreshAll()
  await nextTick()
  renderChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.kpi-container {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.kpi-card {
  padding: 16px;
}

.kpi-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.kpi-icon.blue {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.kpi-icon.green {
  background: rgba(16, 185, 129, 0.1);
  color: var(--el-color-success);
}
.kpi-icon.purple {
  background: rgba(139, 92, 246, 0.1);
  color: #8b5cf6;
}
.kpi-icon.orange {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.kpi-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}

.kpi-detail {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.dashboard-header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.timeline-card {
  padding: 8px;
}

.chart-container {
  width: 100%;
  height: 320px;
}

/* ========== 管理员面板 ========== */
.admin-panel {
  padding: 8px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.admin-loading {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.empty-tip {
  text-align: center;
  padding: 32px 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.user-rank-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rank-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  transition: background 0.2s;
}

.rank-row:hover {
  background: var(--el-fill-color-light);
}

.rank-top {
  background: rgba(59, 130, 246, 0.08);
}

.rank-index {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--el-text-color-secondary);
}

.rank-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rank-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.rank-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rank-total-inline {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.rank-model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.rank-model-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  min-width: 0;
}

.rank-model-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.rank-model-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.rank-model-rate {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.rank-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.rank-total {
  font-size: 14px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.rank-rate {
  font-size: 13px;
  font-weight: 600;
}

.admin-pagination-wrap {
  display: flex;
  justify-content: center;
  padding-top: 16px;
}

/* ========== 移动端适配 ========== */

/* ≤768px: KPI 改为双列 */
@media (max-width: 768px) {
  .dashboard {
    gap: 16px;
  }

  .kpi-container {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .kpi-value {
    font-size: 24px;
  }

  .chart-container {
    height: 260px;
  }

  .rank-model-grid {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .rank-row {
    flex-wrap: wrap;
    position: relative;
  }

  .rank-info {
    width: 100%;
    order: 3;
    margin-top: 4px;
  }

  .rank-stats {
    margin-left: auto;
    align-items: flex-end;
  }

  .admin-pagination-wrap :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px 4px;
    white-space: normal;
  }

  .admin-pagination-wrap :deep(.el-pagination__total),
  .admin-pagination-wrap :deep(.el-pagination__jump) {
    display: none;
  }
}

/* ≤480px: KPI 改为单列 */
@media (max-width: 480px) {
  .kpi-container {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .kpi-card {
    padding: 12px;
  }

  .kpi-value {
    font-size: 24px;
  }

  .kpi-detail {
    font-size: 11px;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .chart-container {
    height: 220px;
  }
}
</style>
