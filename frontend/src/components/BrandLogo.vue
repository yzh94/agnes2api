<template>
  <div class="brand-logo" :class="`size-${size}`" :style="{ width: px, height: px }">
    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="brand-logo-svg">
      <defs>
        <linearGradient id="brandGradient_md" x1="8" y1="8" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stop-color="#3b82f6" />
          <stop offset="1" stop-color="#8b5cf6" />
        </linearGradient>
        <linearGradient id="brandGradient_sm" x1="8" y1="8" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stop-color="#3b82f6" />
          <stop offset="1" stop-color="#8b5cf6" />
        </linearGradient>
        <linearGradient id="brandGradient_lg" x1="8" y1="8" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stop-color="#3b82f6" />
          <stop offset="1" stop-color="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="40" height="40" rx="12" :fill="`url(#brandGradient_${size})`" />
      <path
        d="M16 14h6l-2 9 8-9h6L19 36h-6l3-12-3-10z"
        fill="#fff"
        opacity="0.96"
      />
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ size?: 'sm' | 'md' | 'lg' }>(), { size: 'md' })

const sizeMap: Record<string, number> = { sm: 24, md: 32, lg: 48 }
const px = computed(() => `${sizeMap[props.size] ?? 32}px`)
</script>

<style scoped>
.brand-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-logo-svg {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
