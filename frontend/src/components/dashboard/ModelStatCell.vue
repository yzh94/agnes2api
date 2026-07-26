<template>
  <div class="model-stat-cell">
    <div class="stat-info">
      <span class="label">成功: {{ stat.success || 0 }}</span>
      <span class="label">失败: {{ stat.failure || 0 }}</span>
    </div>
    <el-progress
      :percentage="stat.success_rate || 0"
      :stroke-width="8"
      :color="getColor(stat.success_rate || 0)"
      :show-text="true"
    />
  </div>
</template>

<script setup lang="ts">
import type { ModelStat } from '@/types/api'

const props = defineProps<{
  stat: ModelStat
}>()

function getColor(rate: number) {
  if (rate > 90) return '#10b981'
  if (rate > 60) return '#f59e0b'
  return '#ef4444'
}
</script>

<style scoped>
.model-stat-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.stat-info .label:first-child {
  color: #10b981;
}

.stat-info .label:last-child {
  color: #ef4444;
}
</style>