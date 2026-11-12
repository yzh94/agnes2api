import type { EChartsOption } from 'echarts'

interface TimelinePoint {
  timestamp: string
  text?: { success_rate: number | null }
  image?: { success_rate: number | null }
  video?: { success_rate: number | null }
}

export function buildDashboardChartOption(
  labels: string[],
  textRates: (number | null)[],
  imageRates: (number | null)[],
  videoRates: (number | null)[],
): EChartsOption {
  return {
    title: { text: '' },
    animationDuration: 800,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: '#334155',
      textStyle: { color: '#f8fafc' },
      axisPointer: { type: 'line', lineStyle: { color: '#475569' } },
      formatter: (params: any) => {
        let html = params[0]?.axisValue + '<br/>'
        params.forEach((p: any) => {
          html += `${p.marker} ${p.seriesName}: ${p.value == null ? '无请求' : p.value + '%'}<br/>`
        })
        return html
      },
    },
    legend: { data: ['文本', '图像', '视频'], bottom: 0, textStyle: { color: '#94a3b8' } },
    grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisTick: { alignWithLabel: true },
      axisLine: { lineStyle: { color: '#334155' } },
      // 60 个 30 秒点，每 10 点（5 分钟）显示一个刻度
      axisLabel: { color: '#94a3b8', interval: 9 },
    },
    yAxis: {
      type: 'value',
      name: '成功率 (%)',
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { formatter: '{value}%', color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#1e293b' } },
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
  }
}
