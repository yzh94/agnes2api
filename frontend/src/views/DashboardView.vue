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

    <!-- 时间序列折线图 - 全局视角 -->
    <el-card shadow="never" class="timeline-card">
      <template #header>
        <span class="card-title">近24小时全局模型成功率趋势</span>
      </template>
      <div ref="chartRef" class="chart-container"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, onUnmounted, watch, nextTick } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import * as echarts from 'echarts'

const dashboardStore = useDashboardStore()
const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

// 刷新看板全部数据：时间序列
const refreshing = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

async function refreshAll() {
  refreshing.value = true
  try {
    await dashboardStore.refreshDashboard()
  } finally {
    refreshing.value = false
  }
}

// 自动刷新：每 10s 刷新看板数据
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
    if (!d.timestamp) return '---'
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

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.chart-container {
  width: 100%;
  height: 320px;
}

/* ========== 移动端适配 ========== */

@media (max-width: 768px) {
  .dashboard {
    gap: 16px;
  }

  .chart-container {
    height: 260px;
  }
}

@media (max-width: 480px) {
  .kpi-value {
    font-size: 24px;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .chart-container {
    height: 220px;
  }
}
</style>
