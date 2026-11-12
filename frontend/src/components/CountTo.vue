<template>
  <span class="count-to">{{ displayValue }}{{ suffix }}</span>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{ to: number; duration?: number; suffix?: string; key?: string }>(), {
  duration: 600,
  suffix: '',
})

const from = ref(0)
const displayValue = computed(() => Math.round(from.value).toLocaleString())

let rafId = 0
let startTime = 0
let fromVal = 0
let toVal = 0

function animate(timestamp: number) {
  if (!startTime) startTime = timestamp
  const progress = Math.min((timestamp - startTime) / props.duration, 1)
  const eased = 1 - Math.pow(1 - progress, 3)
  from.value = fromVal + (toVal - fromVal) * eased
  if (progress < 1) {
    rafId = requestAnimationFrame(animate)
  }
}

watch(
  () => props.to,
  (val) => {
    cancelAnimationFrame(rafId)
    fromVal = from.value
    toVal = val
    startTime = 0
    rafId = requestAnimationFrame(animate)
  },
  { immediate: true },
)

onUnmounted(() => cancelAnimationFrame(rafId))
</script>
