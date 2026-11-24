import { computed, ref, watch } from 'vue'

const hourMs = 3_600_000
const lastUtcHour = Date.UTC(9999, 11, 31, 23)

export function formatHour(iso) {
  return iso.slice(0, 16).replace('T', ' ')
}

export function optionalForecastNumber(input) {
  if (input === '' || input == null) return null
  const value = Number(input)
  if (!Number.isFinite(value)) throw new Error('请填写有效数值，或在缺测时留空。')
  return value
}

export function useHourlyTrial({ startAt, length, fields, readBody, post }) {
  const assessment = ref(null)
  const error = ref('')
  const busy = ref(false)
  let sequence = 0

  const utcStart = computed(() => {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:00$/.test(startAt.value) || startAt.value.startsWith('0000')) return null
    const iso = `${startAt.value}:00.000Z`
    const time = Date.parse(iso)
    if (!Number.isFinite(time) || new Date(time).toISOString() !== iso) return null
    return time + (length - 1) * hourMs <= lastUtcHour ? time : null
  })
  const hourLabels = computed(() => utcStart.value === null ? [] :
    Array.from({ length }, (_, i) => formatHour(new Date(utcStart.value + i * hourMs).toISOString())))

  function invalidate() {
    sequence++
    assessment.value = null
    error.value = ''
    busy.value = false
  }
  watch([startAt, ...fields], invalidate, { deep: true, flush: 'sync' })

  async function calculate() {
    if (busy.value) return
    const request = ++sequence
    assessment.value = null
    error.value = ''
    busy.value = true
    try {
      if (utcStart.value === null) throw new Error('请输入有效的 UTC 整点，且所有预报时次必须在日期范围内。')
      const result = await post({ start_at: `${startAt.value}:00Z`, ...readBody() })
      if (request === sequence) assessment.value = result
    } catch (e) {
      if (request === sequence) error.value = e.message
    } finally {
      if (request === sequence) busy.value = false
    }
  }

  return { assessment, error, busy, hourLabels, invalidate, calculate }
}
