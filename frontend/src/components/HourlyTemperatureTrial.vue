<template>
  <section class="card" aria-label="高温试算输入">
    <header class="card-head"><h3 class="card-title">高温 · 未来 24 小时</h3></header>
    <p class="muted">初始值是教学示例。请填同一地点的逐时气温预报；缺测留空，0 表示 0 °C。</p>
    <form @input="invalidate" @submit.prevent="calculate">
      <div class="temperature-meta">
        <div class="field">
          <label class="field-label" for="temperature-location">地点</label>
          <input id="temperature-location" v-model="location" required maxlength="80" />
        </div>
        <div class="field">
          <label class="field-label" for="temperature-start">预测起点（UTC 整点）</label>
          <input id="temperature-start" v-model="startAt" type="datetime-local" required step="3600" />
        </div>
      </div>
      <fieldset class="temperature-window">
        <legend>24 个 UTC 时次的预报气温（°C）</legend>
        <div class="temperature-slots">
          <div v-for="(_, i) in temperatures" :key="i" class="field">
            <label class="field-label" :for="`temperature-hour-${i + 1}`">
              第 {{ i + 1 }} 小时气温 <span class="temperature-time">{{ hourLabels[i] ?? '—' }}</span>
            </label>
            <input :id="`temperature-hour-${i + 1}`" v-model="temperatures[i]" type="number" step="any" placeholder="缺测" />
          </div>
        </div>
      </fieldset>
      <button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? '正在试算…' : '计算高温风险' }}</button>
      <button class="btn btn-ghost" type="button" @click="resetSample">恢复教学示例</button>
      <p v-if="error" class="alert alert--error temperature-alert" role="alert">{{ error }}</p>
    </form>
  </section>

  <section v-if="assessment" class="card" aria-label="高温预测结果" aria-live="polite">
    <header class="card-head"><h3 class="card-title">高温预测结果 · {{ assessment.location }}</h3></header>
    <p class="muted">{{ formatHour(assessment.start_at) }} 至 {{ formatHour(assessment.end_at) }}（UTC，含首末时次） · 有效气温 {{ assessment.usable_hours }} / 24 小时</p>
    <p><strong data-testid="temperature-outcome">{{ outcomeLabels[assessment.outcome] }}</strong></p>
    <template v-if="assessment.extreme_c !== null">
      <p>窗口最高气温 <strong data-testid="temperature-extreme">{{ assessment.extreme_c }} °C</strong></p>
      <p v-if="assessment.qualifying_hours.length" data-testid="temperature-qualifying">
        达标时次（UTC）：{{ assessment.qualifying_hours.map(formatHour).join('、') }}
      </p>
    </template>
    <p v-else>逐时气温有缺测，不计算窗口最高值或达标时次。</p>
    <p class="muted">教学线：窗口最高气温 ≥ {{ assessment.threshold_c.toFixed(1) }} °C。此结果不是官方高温预警。</p>
  </section>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api'

const hourCount = 24
const hourMs = 3_600_000
const sample = {
  location: '课程示例点', startAt: '2025-07-01T00:00',
  temperatures: [24, 24, 23, 23, 22, 23, 24, 26, 28, 30, 32, 33, 34, 34.9, 34, 33, 32, 30, 29, 28, 27, 26, 25, 24]
}
const location = ref(sample.location)
const startAt = ref(sample.startAt)
const temperatures = ref([...sample.temperatures])
const assessment = ref(null)
const error = ref('')
const busy = ref(false)
let sequence = 0
const outcomeLabels = { REACHED: '达到高温教学阈值', NOT_REACHED: '未达高温教学阈值', INSUFFICIENT: '无法判断' }

function formatHour(iso) {
  return iso.slice(0, 16).replace('T', ' ')
}

const utcStart = computed(() => {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:00$/.test(startAt.value) || startAt.value.startsWith('0000')) return null
  const iso = `${startAt.value}:00.000Z`
  const time = Date.parse(iso)
  if (!Number.isFinite(time) || new Date(time).toISOString() !== iso) return null
  if (time + (hourCount - 1) * hourMs > Date.UTC(9999, 11, 31, 23)) return null
  return time
})
const hourLabels = computed(() => utcStart.value === null ? [] :
  Array.from({ length: hourCount }, (_, i) => formatHour(new Date(utcStart.value + i * hourMs).toISOString())))

function invalidate() {
  sequence++
  assessment.value = null
  error.value = ''
  busy.value = false
}
// A raw input event also clears results when an invalid native edit doesn't change the model.
watch([location, startAt, temperatures], invalidate, { deep: true, flush: 'sync' })
onUnmounted(invalidate)

function resetSample() {
  location.value = sample.location
  startAt.value = sample.startAt
  temperatures.value = [...sample.temperatures]
}

function optionalNumber(input) {
  if (input === '' || input == null) return null
  const value = Number(input)
  if (!Number.isFinite(value)) throw new Error('请填写有效的气温，或在缺测时留空。')
  return value
}

async function calculate() {
  if (busy.value) return
  const request = ++sequence
  assessment.value = null
  error.value = ''
  busy.value = true
  try {
    if (utcStart.value === null) throw new Error('请输入有效的 UTC 整点，且后续 23 小时必须在日期范围内。')
    const payload = {
      location: location.value.trim(), start_at: `${startAt.value}:00Z`,
      hourly_temperature_c: temperatures.value.map(optionalNumber)
    }
    const response = await apiFetch('/basic-forecast/heat/assessment', { method: 'POST', body: JSON.stringify(payload) })
    if (request === sequence) assessment.value = response
  } catch (e) {
    if (request === sequence) error.value = e.message
  } finally {
    if (request === sequence) busy.value = false
  }
}
</script>

<style scoped>
.temperature-meta, .temperature-slots {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));
  gap: 4px 12px;
}
.temperature-meta { grid-template-columns: repeat(auto-fit, minmax(min(100%, 225px), 1fr)); }
.temperature-meta .field, .temperature-slots .field, .temperature-window { min-width: 0; }
.temperature-window { margin: 2px 0 14px; padding: 10px 12px 0; border: 1px solid var(--border); }
.temperature-window legend { padding: 0 6px; }
.temperature-time { display: block; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.temperature-alert { margin: 12px 0 0; }
</style>
