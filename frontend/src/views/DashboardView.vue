<template>
  <div class="dashboard">
    <!-- 右上角刷新控制 -->
    <div class="dashboard-header">
      <div class="header-info">
        <span class="header-time mono-font">{{ currentTime }}</span>
      </div>
      <div class="header-actions">
        <el-switch
          v-model="dashboardStore.autoRefresh"
          active-text="自动刷新"
          inline-prompt
        />
        <el-button @click="refreshAll" :loading="refreshing" size="small">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 用户当日模型成功率卡片 -->
    <div class="kpi-container">
      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon blue"><el-icon><ChatDotRound /></el-icon></div>
          <div class="kpi-label">文本模型</div>
          <div class="kpi-tag mono-font">文本</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.text.success_rate) }">
          <CountTo :to="stats.text.success_rate" suffix="%" />
        </div>
        <div class="kpi-detail mono-font">
          总计 <CountTo :to="stats.text.total" /> ·
          成功 <CountTo :to="stats.text.success" /> ·
          失败 <CountTo :to="stats.text.failure" />
        </div>
        <div class="kpi-bar-wrap">
          <div class="kpi-bar" :style="{ width: Math.min(stats.text.success_rate, 100) + '%', background: getSuccessColor(stats.text.success_rate) }"></div>
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon green"><el-icon><Picture /></el-icon></div>
          <div class="kpi-label">图像模型</div>
          <div class="kpi-tag mono-font">图像</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.image.success_rate) }">
          <CountTo :to="stats.image.success_rate" suffix="%" />
        </div>
        <div class="kpi-detail mono-font">
          总计 <CountTo :to="stats.image.total" /> ·
          成功 <CountTo :to="stats.image.success" /> ·
          失败 <CountTo :to="stats.image.failure" />
        </div>
        <div class="kpi-bar-wrap">
          <div class="kpi-bar" :style="{ width: Math.min(stats.image.success_rate, 100) + '%', background: getSuccessColor(stats.image.success_rate) }"></div>
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon purple"><el-icon><VideoCamera /></el-icon></div>
          <div class="kpi-label">视频模型</div>
          <div class="kpi-tag mono-font">视频</div>
        </div>
        <div class="kpi-value" :style="{ color: getSuccessColor(stats.video.success_rate) }">
          <CountTo :to="stats.video.success_rate" suffix="%" />
        </div>
        <div class="kpi-detail mono-font">
          总计 <CountTo :to="stats.video.total" /> ·
          成功 <CountTo :to="stats.video.success" /> ·
          失败 <CountTo :to="stats.video.failure" />
        </div>
        <div class="kpi-bar-wrap">
          <div class="kpi-bar" :style="{ width: Math.min(stats.video.success_rate, 100) + '%', background: getSuccessColor(stats.video.success_rate) }"></div>
        </div>
      </el-card>

      <el-card class="kpi-card" shadow="never">
        <div class="kpi-header">
          <div class="kpi-icon orange"><el-icon><Odometer /></el-icon></div>
          <div class="kpi-label">当日总计</div>
          <div class="kpi-tag mono-font">汇总</div>
        </div>
        <div class="kpi-value"><CountTo :to="stats.summary.total" /></div>
        <div class="kpi-detail mono-font">
          成功率 <CountTo :to="stats.summary.success_rate" suffix="%" />
        </div>
        <div class="kpi-bar-wrap">
          <div class="kpi-bar" :style="{ width: Math.min(stats.summary.success_rate, 100) + '%', background: 'var(--warning)' }"></div>
        </div>
      </el-card>
    </div>

    <!-- 时间序列折线图 -->
    <el-card shadow="never" class="timeline-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">全局成功率趋势 · 最近 30 分钟</span>
          <span class="card-subtitle mono-font">实时数据</span>
        </div>
      </template>
      <div v-loading="chartLoading" element-loading-text="加载中...">
        <div ref="chartRef" class="chart-container"></div>
      </div>
    </el-card>

    <!-- 管理员看板：上游 URL 成功率（仅 admin） -->
    <el-card v-if="authStore.role === 'admin'" shadow="never" class="admin-panel">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">上游通道成功率</span>
          <span class="card-subtitle mono-font">AGNES_BASE_URL · 最近 100 次请求</span>
        </div>
      </template>
      <div v-if="!adminDataLoaded && adminLoading" class="admin-loading">加载中...</div>
      <div v-else class="url-stat-list">
        <div v-for="item in urlStats" :key="item.url" class="url-stat-row">
          <div class="url-stat-main">
            <span class="url-stat-name mono-font">{{ item.url }}</span>
            <el-tag v-if="item.is_best" size="small" type="success" effect="dark">当前使用</el-tag>
            <el-tag v-else-if="item.total === 0" size="small" type="info" effect="plain">待验证</el-tag>
          </div>
          <div class="url-stat-bar-wrap">
            <div class="url-stat-bar" :style="{ width: Math.min(item.success_rate, 100) + '%', background: getSuccessColor(item.success_rate) }"></div>
          </div>
          <div class="url-stat-meta">
            <span class="url-stat-rate mono-font" :style="{ color: getSuccessColor(item.success_rate) }">{{ item.success_rate }}%</span>
            <span class="url-stat-detail mono-font">总计 {{ item.total }} · 成功 {{ item.success }} · 失败 {{ item.failure }}</span>
          </div>
        </div>
        <div v-if="!adminLoading && urlStats.length === 0" class="empty-tip">暂无数据</div>
      </div>
    </el-card>

    <!-- 管理员看板：Key 池模型统计 -->
    <el-card v-if="authStore.role === 'admin'" shadow="never" class="admin-panel">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">Key 池聚合统计</span>
          <span class="card-subtitle mono-font">全部密钥 · 每日 00:00 重置</span>
        </div>
      </template>
      <div v-if="!adminDataLoaded && adminLoading" class="admin-loading">加载中...</div>
      <div v-else class="kpi-container">
        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon blue"><el-icon><ChatDotRound /></el-icon></div>
            <div class="kpi-label">文本模型</div>
            <div class="kpi-tag mono-font">文本</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.text.success_rate) }">
            <CountTo :to="adminKeyPool.text.success_rate" suffix="%" />
          </div>
          <div class="kpi-detail mono-font">
            总计 <CountTo :to="adminKeyPool.text.total" /> ·
            成功 <CountTo :to="adminKeyPool.text.success" /> ·
            失败 <CountTo :to="adminKeyPool.text.failure" />
          </div>
          <div class="kpi-bar-wrap">
            <div class="kpi-bar" :style="{ width: Math.min(adminKeyPool.text.success_rate, 100) + '%', background: getSuccessColor(adminKeyPool.text.success_rate) }"></div>
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon green"><el-icon><Picture /></el-icon></div>
            <div class="kpi-label">图像模型</div>
            <div class="kpi-tag mono-font">图像</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.image.success_rate) }">
            <CountTo :to="adminKeyPool.image.success_rate" suffix="%" />
          </div>
          <div class="kpi-detail mono-font">
            总计 <CountTo :to="adminKeyPool.image.total" /> ·
            成功 <CountTo :to="adminKeyPool.image.success" /> ·
            失败 <CountTo :to="adminKeyPool.image.failure" />
          </div>
          <div class="kpi-bar-wrap">
            <div class="kpi-bar" :style="{ width: Math.min(adminKeyPool.image.success_rate, 100) + '%', background: getSuccessColor(adminKeyPool.image.success_rate) }"></div>
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon purple"><el-icon><VideoCamera /></el-icon></div>
            <div class="kpi-label">视频模型</div>
            <div class="kpi-tag mono-font">视频</div>
          </div>
          <div class="kpi-value" :style="{ color: getSuccessColor(adminKeyPool.video.success_rate) }">
            <CountTo :to="adminKeyPool.video.success_rate" suffix="%" />
          </div>
          <div class="kpi-detail mono-font">
            总计 <CountTo :to="adminKeyPool.video.total" /> ·
            成功 <CountTo :to="adminKeyPool.video.success" /> ·
            失败 <CountTo :to="adminKeyPool.video.failure" />
          </div>
          <div class="kpi-bar-wrap">
            <div class="kpi-bar" :style="{ width: Math.min(adminKeyPool.video.success_rate, 100) + '%', background: getSuccessColor(adminKeyPool.video.success_rate) }"></div>
          </div>
        </el-card>

        <el-card class="kpi-card" shadow="never">
          <div class="kpi-header">
            <div class="kpi-icon orange"><el-icon><Odometer /></el-icon></div>
            <div class="kpi-label">全 Key 总计</div>
            <div class="kpi-tag mono-font">汇总</div>
          </div>
          <div class="kpi-value"><CountTo :to="adminKeyPool.summary.total" /></div>
          <div class="kpi-detail mono-font">
            Key 归属 <CountTo :to="adminKeyPool.summary.success_rate" suffix="%" /> ·
            请求级 <span :style="{ color: getSuccessColor(adminRequestLevel.summary.success_rate) }"><CountTo :to="adminRequestLevel.summary.success_rate" suffix="%" /></span>
          </div>
          <div class="kpi-bar-wrap">
            <div class="kpi-bar" :style="{ width: Math.min(adminKeyPool.summary.success_rate, 100) + '%', background: 'var(--warning)' }"></div>
          </div>
        </el-card>
      </div>

      <!-- 失败原因构成（累计，重置 Key 池时清零） -->
      <div v-if="failureReasonTotal > 0" class="failure-reason-bar">
        <span class="fr-label mono-font">失败构成</span>
        <span v-for="item in failureReasonItems" :key="item.key" class="fr-item mono-font">
          <span class="fr-dot" :style="{ background: item.color }"></span>{{ item.label }} {{ item.count }}
        </span>
      </div>
    </el-card>

    <!-- 管理员看板：用户请求次数排名 -->
    <el-card v-if="authStore.role === 'admin'" shadow="never" class="admin-panel">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">用户请求排名</span>
          <span class="card-subtitle mono-font">每日统计 · 00:00 重置</span>
        </div>
      </template>
      <div v-if="!adminDataLoaded && adminLoading" class="admin-loading">加载中...</div>
      <div v-else class="user-rank-list">
        <div v-for="(item, idx) in adminUserRanking" :key="item.user_id" class="rank-row" :class="{ 'rank-top': globalIdx(idx) < 3 }">
          <div class="rank-index">
            <el-tag v-if="globalIdx(idx) === 0" type="warning" size="small" effect="dark">第 1 名</el-tag>
            <el-tag v-else-if="globalIdx(idx) === 1" type="info" size="small" effect="plain">第 2 名</el-tag>
            <el-tag v-else-if="globalIdx(idx) === 2" type="danger" size="small" effect="plain">第 3 名</el-tag>
            <span v-else class="mono-font rank-num">{{ globalIdx(idx) + 1 }}</span>
          </div>
          <div class="rank-info">
            <div class="rank-main">
              <span class="rank-name mono-font">{{ item.username }}</span>
              <span class="rank-total-inline mono-font">请求: {{ item.total_requests.toLocaleString() }}</span>
            </div>
            <div class="rank-model-grid">
              <div class="rank-model-item">
                <span class="rank-model-label mono-font">文本</span>
                <span class="rank-model-count mono-font">{{ item.text_requests }}</span>
                <span class="rank-model-rate mono-font" :style="{ color: getSuccessColor(item.text_success_rate) }">{{ item.text_success_rate }}%</span>
              </div>
              <div class="rank-model-item">
                <span class="rank-model-label mono-font">图像</span>
                <span class="rank-model-count mono-font">{{ item.image_requests }}</span>
                <span class="rank-model-rate mono-font" :style="{ color: getSuccessColor(item.image_success_rate) }">{{ item.image_success_rate }}%</span>
              </div>
              <div class="rank-model-item">
                <span class="rank-model-label mono-font">视频</span>
                <span class="rank-model-count mono-font">{{ item.video_requests }}</span>
                <span class="rank-model-rate mono-font" :style="{ color: getSuccessColor(item.video_success_rate) }">{{ item.video_success_rate }}%</span>
              </div>
            </div>
          </div>
          <div class="rank-stats">
            <span class="rank-total mono-font">{{ item.total_requests.toLocaleString() }}</span>
            <span class="rank-rate mono-font" :style="{ color: getSuccessColor(item.success_rate) }">{{ item.success_rate }}%</span>
          </div>
        </div>
        <div v-if="!adminLoading && adminUserRanking.length === 0" class="empty-tip">暂无数据</div>
      </div>
      <div v-if="adminPagination && adminPagination.total_pages > 1" class="admin-pagination-wrap">
        <el-pagination
          v-model:current-page="adminPage"
          :page-size="adminPageSize"
          :total="adminPagination.total"
          layout="prev, pager, next"
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
import { fetchAdminDashboard, fetchUpstreamUrlStats } from '@/services/api'
import type { GlobalModelStats, AdminUserRanking, AdminPagination, UpstreamUrlStat } from '@/types/api'
import CountTo from '@/components/CountTo.vue'
import { buildDashboardChartOption } from '@/utils/chart-config'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()
const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null
const chartLoading = ref(false)

const stats = computed(() => dashboardStore.userStats)

// 实时时间显示（北京时间 UTC+8，与后端统计时区一致）
const timeFormatter = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})
const currentTime = ref('')
setInterval(() => {
  currentTime.value = timeFormatter.format(new Date()) + ' UTC+8'
}, 1000)

const EMPTY_MODEL_STATS: GlobalModelStats = {
  text: { total: 0, success: 0, failure: 0, success_rate: 0 },
  image: { total: 0, success: 0, failure: 0, success_rate: 0 },
  video: { total: 0, success: 0, failure: 0, success_rate: 0 },
  summary: { total: 0, success: 0, failure: 0, success_rate: 0 },
}
const adminKeyPool = ref<GlobalModelStats>({ ...EMPTY_MODEL_STATS })
const adminRequestLevel = ref<GlobalModelStats>({ ...EMPTY_MODEL_STATS })
const adminFailureReasons = ref<Record<string, number>>({})
const adminUserRanking = ref<AdminUserRanking[]>([])
const urlStats = ref<UpstreamUrlStat[]>([])
const adminLoading = ref(false)
const adminDataLoaded = ref(false)
const adminPage = ref(1)
const adminPageSize = ref(10)
const adminPagination = ref<AdminPagination | null>(null)

function getSuccessColor(rate: number) {
  if (rate > 90) return 'var(--success)'
  if (rate > 60) return 'var(--warning)'
  return 'var(--danger)'
}

function globalIdx(localIdx: number) {
  return (adminPage.value - 1) * adminPageSize.value + localIdx
}

// 失败原因分类元数据（与后端 KEY:POOL:fail_reasons 的 reason 对应）
const FAILURE_REASON_META: Record<string, { label: string; color: string }> = {
  rate_limit: { label: '限流 429', color: 'var(--warning)' },
  auth: { label: '鉴权 401/403', color: 'var(--danger)' },
  server: { label: '服务端 408/5xx', color: 'var(--accent-light)' },
  network: { label: '网络异常', color: 'var(--info)' },
  zero_chunk: { label: '空流', color: 'var(--text-tertiary)' },
}
const failureReasonTotal = computed(() =>
  Object.values(adminFailureReasons.value).reduce((a, b) => a + b, 0)
)
const failureReasonItems = computed(() =>
  Object.entries(FAILURE_REASON_META)
    .filter(([k]) => (adminFailureReasons.value[k] ?? 0) > 0)
    .map(([k, meta]) => ({ key: k, label: meta.label, color: meta.color, count: adminFailureReasons.value[k] }))
)

async function loadAdminData() {
  if (authStore.role !== 'admin') return
  adminLoading.value = true
  try {
    const res = await fetchAdminDashboard(adminPage.value, adminPageSize.value)
    adminKeyPool.value = res.key_pool ?? EMPTY_MODEL_STATS
    adminRequestLevel.value = res.request_level ?? { ...EMPTY_MODEL_STATS }
    adminFailureReasons.value = res.failure_reasons ?? {}
    adminUserRanking.value = res.user_ranking || []
    adminPagination.value = res.pagination || null
    urlStats.value = await fetchUpstreamUrlStats()
  } catch { /* http interceptor handles errors */ }
  finally {
    adminLoading.value = false
    adminDataLoaded.value = true
  }
}

function handleAdminPageChange(page: number) {
  adminPage.value = page
  loadAdminData()
}

const refreshing = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

async function refreshAll() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await Promise.all([dashboardStore.refreshDashboard(), loadAdminData()])
  } finally {
    refreshing.value = false
  }
}

watch(() => dashboardStore.autoRefresh, (val) => {
  if (val) {
    refreshTimer = setInterval(refreshAll, 10000)
  } else if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

const emptyChartOption = {
  title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#4a6fa5', fontSize: 14 } },
  xAxis: { type: 'category', data: [] },
  yAxis: { type: 'value', name: '成功率 (%)', min: 0, max: 100 },
  series: [],
}

function renderChart() {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  const data = dashboardStore.timelineData
  if (!data || data.length === 0) {
    chartInstance.setOption(emptyChartOption, true)
    return
  }
  const labels = data.map((d) => d.timestamp.split('T')[1].slice(0, 8))
  const toRate = (v?: number | null) => (v == null ? 100 : +v.toFixed(2))
  const textRates = data.map((d) => toRate(d.text?.success_rate))
  const imageRates = data.map((d) => toRate(d.image?.success_rate))
  const videoRates = data.map((d) => toRate(d.video?.success_rate))
  chartInstance.setOption(buildDashboardChartOption(labels, textRates, imageRates, videoRates), true)
}

watch(() => dashboardStore.timelineData, () => {
  nextTick(() => renderChart())
}, { deep: true, flush: 'post' })

function handleResize() {
  chartInstance?.resize()
}

onMounted(async () => {
  chartLoading.value = true
  try { await refreshAll() }
  finally { chartLoading.value = false }
  await nextTick()
  renderChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* KPI Cards */
.kpi-container {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.kpi-card {
  position: relative;
  overflow: hidden;
}

.kpi-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.kpi-icon {
  width: 32px; height: 32px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.kpi-icon.blue   { background: var(--info-dim); color: var(--info); }
.kpi-icon.green  { background: var(--success-dim); color: var(--success); }
.kpi-icon.purple { background: var(--accent-dim); color: var(--accent-light); }
.kpi-icon.orange { background: var(--warning-dim); color: var(--warning); }

.kpi-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.kpi-tag {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
  letter-spacing: -0.5px;
  font-family: var(--el-font-family-mono);
}

.kpi-detail {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 10px;
}

.kpi-bar-wrap {
  height: 3px;
  background: var(--bg-elevated);
  border-radius: 2px;
  overflow: hidden;
}

.kpi-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Timeline Card */
.timeline-card {
  padding: 0;
}

.card-header-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-subtitle {
  font-size: 11px;
  color: var(--text-muted);
}

.chart-container {
  width: 100%;
  height: 300px;
}

.admin-panel {
  padding: 0;
}

.admin-loading {
  text-align: center;
  padding: 40px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.empty-tip {
  text-align: center;
  padding: 32px 0;
  color: var(--text-muted);
  font-size: 13px;
}

/* Upstream URL Stat List */
.url-stat-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px;
}

.url-stat-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--bg-secondary);
}

.url-stat-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.url-stat-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.url-stat-bar-wrap {
  width: 160px;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
  flex-shrink: 0;
}

.url-stat-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.url-stat-meta {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-shrink: 0;
}

.url-stat-rate {
  font-size: 14px;
  font-weight: 700;
  min-width: 56px;
  text-align: right;
}

.url-stat-detail {
  font-size: 11px;
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .url-stat-row {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .url-stat-bar-wrap { width: 100%; }
  .url-stat-meta { justify-content: space-between; }
  .url-stat-rate { text-align: left; }
}

/* User Rank List */
.user-rank-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 16px;
}

.rank-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-radius: 6px;
  transition: background 0.15s;
  border: 1px solid transparent;
}

.rank-row:hover {
  background: var(--bg-elevated);
}

.rank-top {
  background: var(--bg-secondary);
}

.rank-index {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-tertiary);
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
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rank-total-inline {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.rank-model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.rank-model-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 4px;
  background: var(--bg-secondary);
  min-width: 0;
}

.rank-model-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
}

.rank-model-count {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.rank-model-rate {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.rank-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.rank-total {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--el-font-family-mono);
}

.rank-rate {
  font-size: 11px;
  font-weight: 600;
}

.admin-pagination-wrap {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}

/* 失败原因构成条 */
.failure-reason-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--bg-secondary);
  font-size: 12px;
}

.fr-label {
  color: var(--text-tertiary);
  font-weight: 600;
  letter-spacing: 1px;
}

.fr-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
}

.fr-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

/* 响应式 */
@media (max-width: 1024px) {
  .kpi-container { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .dashboard { gap: 12px; }
  .kpi-container { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .kpi-value { font-size: 24px; }
  .chart-container { height: 220px; }
  .rank-model-grid { grid-template-columns: 1fr; gap: 4px; }
  .rank-row { flex-wrap: wrap; position: relative; }
  .rank-info { width: 100%; order: 3; margin-top: 4px; }
  .rank-stats { margin-left: auto; align-items: flex-end; }
}
@media (max-width: 480px) {
  .kpi-container { grid-template-columns: 1fr; gap: 10px; }
  .kpi-value { font-size: 22px; }
  .kpi-detail { font-size: 10px; }
  .header-actions { flex-wrap: wrap; }
  .chart-container { height: 200px; }
}
</style>
