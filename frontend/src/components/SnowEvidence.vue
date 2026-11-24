<template>
  <section class="card" aria-label="雪灾预报判定">
    <header class="card-head">
      <h3 class="card-title">{{ assessment.case.name }}</h3>
      <span class="card-subtitle">24 小时 · UTC · 教学研判</span>
    </header>

    <div class="snow-result">
      <div>
        <div class="detail-label">累计预报降雪</div>
        <div class="snow-amount" data-testid="snow-total">{{ metric ? `${metric.value.toFixed(2)} cm` : '—' }}</div>
        <div class="muted">{{ metric ? `教学阈值 ≥ ${metric.threshold.toFixed(2)} cm` : `有效输入 ${assessment.usable_hours}/24 小时` }}</div>
      </div>
      <div role="status">
        <h4>{{ resultText }}</h4>
        <p v-if="!metric" class="muted">需 24 个完整的逐时降雪量与 2 米气温。缺测不会按零填写。</p>
        <p v-else class="muted">最低预报气温 {{ assessment.min_temperature_c.toFixed(1) }} °C；气温仅供解释，不改变判定。</p>
      </div>
    </div>

    <dl class="snow-meta">
      <div><dt>模式起报</dt><dd>{{ stamp(assessment.case.initialized_at) }}</dd></div>
      <div><dt>研判窗口（起报后 12 小时开始）</dt><dd>{{ stamp(assessment.case.window_start) }} 至 {{ stamp(assessment.forecast_window_end) }}</dd></div>
      <div v-if="assessment.snow_period_start"><dt>首末有雪小时覆盖范围</dt><dd>{{ stamp(assessment.snow_period_start) }} 至 {{ stamp(assessment.snow_period_end) }}（不保证连续）</dd></div>
    </dl>

    <div v-if="metric" class="snow-strip" aria-hidden="true">
      <div v-for="hour in assessment.hours" :key="hour.valid_at" class="snow-strip-cell" :title="`${stamp(hour.valid_at)} 结束：${hour.snowfall_cm.toFixed(2)} cm`">
        <span :style="{ height: `${100 * hour.snowfall_cm / topHourly}%` }"></span>
      </div>
    </div>
    <details class="snow-hours" v-if="assessment.hours.length">
      <summary>查看逐时预报（时间为前一小时降雪量的结束标签）</summary>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">小时末</th><th scope="col">降雪 (cm)</th><th scope="col">2 米气温 (°C)</th></tr></thead>
          <tbody><tr v-for="hour in assessment.hours" :key="hour.valid_at">
            <td>{{ stamp(hour.valid_at) }}</td><td>{{ hour.snowfall_cm?.toFixed(2) ?? '缺测' }}</td><td>{{ hour.temperature_c?.toFixed(1) ?? '缺测' }}</td>
          </tr></tbody>
        </table>
      </div>
    </details>
    <p class="muted snow-source">
      预报：<a :href="assessment.case.forecast_source.url" target="_blank" rel="noopener noreferrer">{{ assessment.case.forecast_source.product }}</a>；
      济南站附近的模式网格 {{ assessment.case.forecast_grid.latitude }}°N, {{ assessment.case.forecast_grid.longitude }}°E；
      {{ assessment.case.forecast_source.checked_on_utc }} 核对。起报并非 API 实际发布时间，结论不代表站点实测、灾损或官方预警。
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ assessment: { type: Object, required: true } })
const metric = computed(() => props.assessment.metric)
const resultText = computed(() => ({
  REACHED: '达到强降雪教学阈值',
  NOT_REACHED: '未达到强降雪教学阈值',
  INSUFFICIENT: '数据不足，无法判断'
})[props.assessment.outcome])
const topHourly = computed(() => Math.max(0.01, ...props.assessment.hours.map(hour => hour.snowfall_cm ?? 0)))

function stamp(value) {
  return `${new Date(value).toISOString().slice(0, 16).replace('T', ' ')} UTC`
}
</script>

<style scoped>
.snow-result { display: flex; flex-wrap: wrap; align-items: end; gap: 0.9rem 2rem; margin-bottom: 14px; }
.snow-result h4, .snow-result p { margin: 0 0 4px; }
.snow-amount { color: var(--accent-text, #9bdcff); font-size: clamp(1.9rem, 5vw, 2.8rem); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.snow-meta { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0 0 13px; }
.snow-meta > div { min-width: 0; }
.snow-meta dt { font-size: 0.78rem; }
.snow-meta dd { margin: 1px 0 0; overflow-wrap: anywhere; }
.snow-strip { display: grid; grid-template-columns: repeat(24, minmax(0, 1fr)); align-items: end; height: 50px; gap: 3px; margin-bottom: 8px; }
.snow-strip-cell { display: flex; align-items: end; height: 100%; border-bottom: 1px solid var(--border); }
.snow-strip-cell span { display: block; width: 100%; background: #70bcdf; border-radius: 2px 2px 0 0; }
.snow-hours summary { cursor: pointer; }
.snow-hours .table-wrap { margin-top: 8px; }
.snow-source { margin: 12px 0 0; overflow-wrap: anywhere; }
</style>
