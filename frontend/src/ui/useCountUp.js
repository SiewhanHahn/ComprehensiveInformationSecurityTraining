import { ref, watch, onUnmounted, unref } from 'vue'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function useCountUp(source, options = {}) {
  const { duration = 800, decimals = 0 } = options
  const display = ref('—')

  let frame = null
  let current = 0

  const format = (value) =>
    decimals > 0
      ? value.toFixed(decimals)
      : Math.round(value).toLocaleString('zh-CN')

  const cancel = () => {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
  }

  const animate = (target) => {
    cancel()
    if (target === null || target === undefined || target === '' || Number.isNaN(Number(target))) {
      display.value = '—'
      return
    }
    const end = Number(target)
    if (prefersReducedMotion() || duration <= 0) {
      current = end
      display.value = format(end)
      return
    }
    const from = current
    const startedAt = performance.now()
    const step = (now) => {
      const t = Math.min(1, (now - startedAt) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      current = from + (end - from) * eased
      display.value = format(current)
      if (t < 1) {
        frame = requestAnimationFrame(step)
      } else {
        current = end
        display.value = format(end)
        frame = null
      }
    }
    frame = requestAnimationFrame(step)
  }

  const read = typeof source === 'function' ? source : () => unref(source)
  watch(read, animate, { immediate: true })
  onUnmounted(cancel)

  return display
}
