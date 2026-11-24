<template>
  <section class="card" aria-label="干旱试算输入">
    <header class="card-head"><h3 class="card-title">干旱 · 未来七天少雨是否持续</h3></header>
    <p class="muted">初始值是教学示例，不是实况。请按同一地点和 UTC 日替换降水预报；未知的输入留空，不填 0。</p>
    <form @submit.prevent="calculate">
      <div class="drought-meta">
        <div class="field">
          <label class="field-label" for="drought-location">地点</label>
          <input id="drought-location" v-model="location" required maxlength="80" />
        </div>
        <div class="field">
          <label class="field-label" for="drought-date">预测首日（UTC）</label>
          <input id="drought-date" v-model="startDate" type="date" required />
        </div>
        <div class="field">
          <label class="field-label" for="drought-antecedent">签发前连续少雨日数</label>
          <input id="drought-antecedent" v-model="antecedent" type="number" min="0" max="3650" step="1" placeholder="未知时留空" />
        </div>
      </div>
      <fieldset class="drought-rain">
        <legend>未来七天逐日总降水（mm）</legend>
        <div class="drought-slots">
          <div v-for="(_, i) in dailyRain" :key="i" class="field">
            <label class="field-label" :for="`drought-rain-${i + 1}`">第 {{ i + 1 }} 天降水</label>
            <input :id="`drought-rain-${i + 1}`" v-model="dailyRain[i]" type="number" min="0" step="any" placeholder="未知" />
          </div>
        </div>
      </fieldset>
      <button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? '正在试算…' : '计算干旱风险' }}</button>
      <button class="btn btn-ghost" type="button" @click="resetSample">恢复教学示例</button>
      <p v-if="error" class="alert alert--error drought-alert" role="alert">{{ error }}</p>
    </form>
  </section>

  <section v-if="assessment" class="card" aria-label="干旱预测结果" aria-live="polite">
    <header class="card-head"><h3 class="card-title">干旱预测结果 · {{ assessment.location }}</h3></header>
    <p class="muted">{{ assessment.start_date }} 至 {{ assessment.end_date }}（UTC，含首末日） · 有效降水 {{ assessment.usable_days }} / 7 天</p>
    <p class="drought-result" data-testid="drought-outcome">{{ outcomeLabels[assessment.outcome] }}</p>
    <p v-if="assessment.end_dry_days !== null">第七天末连续少雨 <strong data-testid="drought-streak">{{ assessment.end_dry_days }} 天</strong></p>
    <p v-else>已有少雨日数或未来降水缺测，无法计算第七天末的天数。</p>
    <p class="muted">日总降水 &lt; {{ assessment.dry_day_below_mm.toFixed(2) }} mm 时延续，达到该值则清零；第七天末 ≥ {{ assessment.continuation_at_least_days }} 天才达教学线。</p>
    <div class="table-wrap">
      <table class="table">
        <caption class="sr-only">逐日输入与当日结束时的连续少雨天数</caption>
        <thead><tr><th scope="col">UTC 日期</th><th scope="col">预报降水（mm）</th><th scope="col">当日末连续少雨（天）</th></tr></thead>
        <tbody>
          <tr v-for="day in assessment.days" :key="day.valid_date">
            <td>{{ day.valid_date }}</td><td>{{ day.rain_mm ?? '缺测' }}</td><td>{{ day.dry_days ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api'

const sample = { location: '课程示例点', date: '2025-07-01', antecedent: 9, rain: [0, 0.2, 0, 0.3, 0, 0.8, 0] }
const location = ref(sample.location)
const startDate = ref(sample.date)
const antecedent = ref(sample.antecedent)
const dailyRain = ref([...sample.rain])
const assessment = ref(null)
const error = ref('')
const busy = ref(false)
let sequence = 0
const outcomeLabels = {
  REACHED: '少雨持续达到教学阈值', NOT_REACHED: '末日未达持续少雨教学阈值', INSUFFICIENT: '无法判断'
}

function invalidate() {
  sequence++
  assessment.value = null
  error.value = ''
  busy.value = false
}
watch([location, startDate, antecedent, dailyRain], invalidate, { deep: true, flush: 'sync' })
onUnmounted(invalidate)

function resetSample() {
  location.value = sample.location
  startDate.value = sample.date
  antecedent.value = sample.antecedent
  dailyRain.value = [...sample.rain]
}

function optionalNumber(input) {
  if (input === '' || input == null) return null
  const number = Number(input)
  if (!Number.isFinite(number)) throw new Error('请填写有效的数值，或在缺测时留空。')
  return number
}

async function calculate() {
  if (busy.value) return
  const request = ++sequence
  assessment.value = null
  error.value = ''
  busy.value = true
  try {
    const payload = {
      location: location.value.trim(), start_date: startDate.value,
      antecedent_dry_days: optionalNumber(antecedent.value), daily_rain_mm: dailyRain.value.map(optionalNumber)
    }
    const response = await apiFetch('/basic-forecast/drought/assessment', { method: 'POST', body: JSON.stringify(payload) })
    if (request === sequence) assessment.value = response
  } catch (e) {
    if (request === sequence) error.value = e.message
  } finally {
    if (request === sequence) busy.value = false
  }
}
</script>

<style scoped>
.drought-meta, .drought-slots { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 4px 14px; }
.drought-rain { margin: 2px 0 14px; padding: 10px 12px 0; border: 1px solid var(--border); }
.drought-rain legend { padding: 0 6px; }
.drought-alert { margin: 12px 0 0; }
.drought-result { font-weight: 650; }
</style>
