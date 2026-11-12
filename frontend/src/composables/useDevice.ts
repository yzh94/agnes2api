import { ref, onMounted, onUnmounted } from 'vue'

export function useDevice(threshold = 768) {
  const isMobile = ref(false)

  function check() {
    isMobile.value = window.innerWidth < threshold
  }

  onMounted(() => {
    check()
    window.addEventListener('resize', check)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', check)
  })

  return { isMobile }
}
