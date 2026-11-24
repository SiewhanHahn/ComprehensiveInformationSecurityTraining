<template>
  <section class="card" aria-label="风雹试算输入">
    <header class="card-head"><h3 class="card-title">风雹 · 未来 6 小时</h3></header>
    <p class="muted">初始值是教学示例。阵风填预报值；冰雹信号选择有、无或缺测。不用阵风推断冰雹。</p>
    <form @input="invalidate" @submit.prevent="calculate">
      <div class="wind-meta">
        <div class="field">
          <label class="field-label" for="wind-hail-location">地点</label>
          <input id="wind-hail-location" v-model="location" required maxlength="80" />
        </div>
        <div class="field">
          <label class="field-label" for="wind-hail-start">预测起点（UTC 整点）</label>
          <input id="wind-hail-start" v-model="startAt" type="datetime-local" required step="3600" />
        </div>
      </div>
      <div class="wind-slots">
        <fieldset v-for="(_, i) in gusts" :key="i" class="wind-slot">
          <legend>{{ hourLabels[i] ?? `第 ${i + 1} 小时` }} UTC</legend>
          <div class="field">
            <label class="field-label" :for="`gust-${i + 1}`">第 {{ i + 1 }} 小时阵风（m/s）</label>
            <input :id="`gust-${i + 1}`" v-model="gusts[i]" type="number" min="0" step="any" placeholder="缺测" />
          </div>
          <div class="field">
            <label class="field-label" :for="`hail-${i + 1}`">第 {{ i + 1 }} 小时冰雹信号</label>
            <select :id="`hail-${i + 1}`" v-model="hailSignals[i]">
              <option :value="true">有明确雹信号</option>
              <option :value="false">明确无雹信号</option>
              <option :value="null">缺测</option>
            </select>
          </div>
        </fieldset>
      </div>
      <button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? '正在试算…' : '计算风雹风险' }}</button>
      <button class="btn btn-ghost" type="button" @click="resetSample">恢复教学示例</button>
      <p v-if="error" class="alert alert--error wind-alert" role="alert">{{ error }}</p>
    </form>
  </section>

  <section v-if="assessment" class="card" aria-label="风雹预测结果" aria-live="polite">
    <header class="card-head wind-heading"><h3 class="card-title">风雹预测结果 · {{ assessment.location }}</h3></header>
    <p class="muted">{{ formatHour(assessment.start_at) }} 至 {{ formatHour(assessment.end_at) }}（UTC，含首末时次）</p>
    <div class="wind-summary">
      <section class="wind-result" aria-label="阵风结论">
        <h4>阵风</h4>
        <p><strong data-testid="gust-outcome">{{ gustLabels[assessment.gust.outcome] }}</strong></p>
        <p class="muted">有效阵风 {{ assessment.gust.usable_hours }} / 6 小时 · 教学线 ≥ {{ assessment.gust.threshold_mps.toFixed(1) }} m/s</p>
        <p v-if="assessment.gust.max_gust_mps !== null">最强阵风 <strong data-testid="gust-peak">{{ assessment.gust.max_gust_mps }} m/s</strong></p>
        <p v-if="assessment.gust.qualifying_hours.length">达线时次（UTC）：{{ assessment.gust.qualifying_hours.map(formatHour).join('、') }}</p>
      </section>
      <section class="wind-result" aria-label="冰雹结论">
        <h4>冰雹信号</h4>
        <p><strong data-testid="hail-outcome">{{ hailLabels[assessment.hail.outcome] }}</strong></p>
        <p class="muted">有效信号 {{ assessment.hail.usable_hours }} / 6 小时 · 缺测不等于无雹信号</p>
        <p v-if="assessment.hail.qualifying_hours.length" data-testid="hail-qualifying">有雹信号的时次（UTC）：{{ assessment.hail.qualifying_hours.map(formatHour).join('、') }}</p>
      </section>
    </div>
    <p class="muted">两项独立判断；此为教学试算，不是官方风雹预警。</p>
  </section>
</template>

<script setup>
import { onUnmounted, ref } from 'vue'
import { apiFetch } from '../api'
import { formatHour, optionalForecastNumber, useHourlyTrial } from '../lib/hourlyForecast.js'

const hourCount = 6
const sample = { location: '课程示例点', startAt: '2025-07-01T21:00', gusts: [8, 10, 13, 15, 16.9, 17] }
const location = ref(sample.location)
const startAt = ref(sample.startAt)
const gusts = ref([...sample.gusts])
const hailSignals = ref(Array(hourCount).fill(false))
const gustLabels = { REACHED: '阵风达到教学阈值', NOT_REACHED: '阵风未达教学阈值', INSUFFICIENT: '阵风缺测，无法判断' }
const hailLabels = { REACHED: '有明确雹信号', NOT_REACHED: '明确无雹信号', INSUFFICIENT: '雹信号缺测，无法判断' }
const { assessment, error, busy, hourLabels, invalidate, calculate } = useHourlyTrial({
  startAt, length: hourCount, fields: [location, gusts, hailSignals],
  readBody: () => ({
    location: location.value.trim(), hourly_gust_mps: gusts.value.map(optionalForecastNumber),
    hourly_hail_signal: hailSignals.value
  }),
  post: (payload) => apiFetch('/basic-forecast/wind-hail/assessment', { method: 'POST', body: JSON.stringify(payload) })
})
onUnmounted(invalidate)

function resetSample() {
  location.value = sample.location
  startAt.value = sample.startAt
  gusts.value = [...sample.gusts]
  hailSignals.value = Array(hourCount).fill(false)
}
</script>

<style scoped>
.wind-meta, .wind-summary, .wind-slots { display: grid; gap: 12px; }
.wind-meta, .wind-summary { grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
.wind-slots { grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); margin-bottom: 14px; }
.wind-slot, .wind-result { min-width: 0; border: 1px solid var(--border); padding: 10px 12px; }
.wind-slot { margin: 0; }
.wind-slot legend { color: var(--color-text-muted); padding: 0 4px; font-variant-numeric: tabular-nums; }
.wind-result { background: var(--color-surface-soft); border-radius: var(--radius-md); }
.wind-result h4 { margin: 0; }
.wind-meta .field, .wind-heading .card-title { min-width: 0; }
.wind-heading .card-title { overflow-wrap: anywhere; }
.wind-alert { margin: 12px 0 0; }
</style>
