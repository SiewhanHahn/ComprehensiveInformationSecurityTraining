<template>
  <section class="card lightning-evidence" aria-label="雷电预报判定">
    <header class="card-head">
      <h3 class="card-title">雷电预报判定 · {{ assessment.case.city.name }} {{ assessment.case.station_id }}</h3>
      <span :class="['badge', color]" data-testid="lightning-outcome">{{ outcomeLabel }}</span>
    </header>
    <dl class="lightning-meta">
      <div><dt class="muted">起报（UTC）</dt><dd>{{ utc(assessment.case.initialized_at) }}</dd></div>
      <div><dt class="muted">研判窗（UTC）</dt><dd>({{ utc(assessment.case.window_start) }}, {{ utc(assessment.forecast_window_end) }}]</dd></div>
      <div><dt class="muted">可用时次</dt><dd>{{ assessment.usable_hours }} / 6</dd></div>
    </dl>
    <p v-if="assessment.metric" class="lightning-peak">
      6 小时最大 LTNG <strong data-testid="lightning-ltng">{{ formatValue(assessment.metric.value) }}</strong>
      <span class="muted">无量纲 · 教学界线 ≥ {{ formatValue(assessment.metric.threshold) }}</span>
    </p>
    <p v-else>有时次缺测，无法判断；不把缺测当作 0。</p>
    <ol class="lightning-slots" aria-label="六个逐小时有效时次（UTC）">
      <li v-for="row in assessment.hours" :key="row.valid_at" :class="{ 'slot-hit': reached.has(row.valid_at) }">
        <time :datetime="row.valid_at">{{ utc(row.valid_at).slice(11) }} UTC</time>
        <strong>{{ row.ltng === null ? '—' : formatValue(row.ltng) }}</strong>
        <small v-if="row.ltng === null">缺测</small>
        <small v-else-if="reached.has(row.valid_at)">达标</small>
        <small v-else class="muted">{{ assessment.metric ? '未达' : '仅展示' }}</small>
      </li>
    </ol>
    <p class="muted lightning-caption">每格是一个有效时刻的模式信号，不代表这一整小时或时次之间的状态。LTNG 不是概率、闪电次数或落点。</p>
    <p class="lightning-source">
      <a :href="assessment.case.forecast_source.url" target="_blank" rel="noopener noreferrer">{{ assessment.case.forecast_source.agency }} · {{ assessment.case.forecast_source.product }}</a>
      <span class="muted">（{{ assessment.case.forecast_source.checked_on_utc }} 核对）</span>
    </p>
    <p class="muted lightning-caption">
      格点 {{ assessment.case.forecast_grid.latitude }}, {{ assessment.case.forecast_grid.longitude }}，仅代表站点附近。
      <template v-if="assessment.case.archive_latest_modified_at">六份原档案最晚修改：{{ utc(assessment.case.archive_latest_modified_at, true) }} UTC（窗口前）。</template>
      <template v-else>原发时间未获核实，仅可回放，不能创建草稿。</template>
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ assessment: { type: Object, required: true } })
const reached = computed(() => new Set(props.assessment.reached_times))
const outcomeLabel = computed(() => ({
  REACHED: '达到教学阈值', NOT_REACHED: '未达教学阈值', INSUFFICIENT: '无法判断'
})[props.assessment.outcome])
const color = computed(() => ({
  REACHED: 'badge--yellow', NOT_REACHED: 'badge--info', INSUFFICIENT: 'badge--neutral'
})[props.assessment.outcome])

function utc(value, seconds = false) {
  return new Date(value).toISOString().slice(0, seconds ? 19 : 16).replace('T', ' ')
}
function formatValue(value) {
  const formatted = value.toFixed(2)
  return Number(formatted) === value ? formatted : String(value)
}
</script>

<style scoped>
.lightning-meta {
  display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 0 0 14px;
  font-variant-numeric: tabular-nums;
}
.lightning-meta dd { margin: 0; overflow-wrap: anywhere; }
.lightning-peak { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 9px; }
.lightning-peak strong { font-size: 1.45rem; line-height: 1; font-variant-numeric: tabular-nums; }
.lightning-slots {
  display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 6px;
  list-style: none; padding: 0; margin: 14px 0 8px;
}
.lightning-slots li {
  display: grid; gap: 1px; padding: 7px 8px; border-top: 2px solid var(--border);
  font-variant-numeric: tabular-nums;
}
.lightning-slots .slot-hit { border-color: #e2b553; background: rgba(226, 181, 83, 0.12); }
.lightning-slots time, .lightning-slots small { font-size: 0.79rem; }
.lightning-caption { margin: 5px 0; }
.lightning-source { margin: 12px 0 0; overflow-wrap: anywhere; }
@media (max-width: 800px) {
  .lightning-slots { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
