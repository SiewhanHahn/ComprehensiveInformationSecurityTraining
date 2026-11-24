<template>
  <section class="card" aria-label="台风预报判定">
    <header class="card-head">
      <h3 class="card-title">{{ assessment.case.name }} · {{ assessment.city.name }}</h3>
      <span class="card-subtitle">编号 {{ assessment.case.storm_number }} · 历史案例</span>
    </header>

    <div class="case-result">
      <div>
        <div class="detail-label">预报点最小距离</div>
        <div class="case-distance" data-testid="typhoon-distance">{{ metric ? `${km(metric.value)} km` : '—' }}</div>
        <span class="badge" :class="assessment.outcome === 'NEAR' ? 'badge--warning' : 'badge--neutral'">
          {{ outcomeText }}
        </span>
        <p v-if="metric" class="muted case-caption">教学接近阈值 ≤ {{ metric.threshold }} km</p>
      </div>
      <dl class="case-times">
        <div><dt>实际签发（UTC）</dt><dd><time :datetime="assessment.case.issued_at">{{ utc(assessment.case.issued_at) }}</time></dd></div>
        <div><dt>24 h 窗口截止（UTC）</dt><dd><time :datetime="assessment.forecast_window_end">{{ utc(assessment.forecast_window_end) }}</time></dd></div>
        <div v-if="closest"><dt>最近预报点有效时刻（UTC）</dt><dd><time :datetime="closest.valid_at">{{ utc(closest.valid_at) }}</time></dd></div>
        <div><dt>城市代表点</dt><dd>{{ position(assessment.city) }}</dd></div>
      </dl>
    </div>

    <div class="case-panels" :class="{ 'case-panels--paired': showVerification }">
      <div class="case-panel">
        <h4>签发时可用 · 公报预报点</h4>
        <div v-if="assessment.forecast_points.length" class="table-wrap">
          <table class="table">
            <thead><tr><th scope="col">有效时刻 (UTC)</th><th scope="col">台风中心坐标</th></tr></thead>
            <tbody>
              <tr v-for="point in assessment.forecast_points" :key="point.valid_at">
                <td>{{ utc(point.valid_at) }}</td><td>{{ position(point) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted">窗口内没有可用的离散预报点。</p>
        <p class="case-source"><a :href="assessment.case.forecast_source.url" target="_blank" rel="noopener noreferrer">{{ assessment.case.forecast_source.agency }} · {{ assessment.case.forecast_source.product }}</a></p>
      </div>
      <div v-if="showVerification" class="case-panel case-panel--verification" aria-label="事后核对">
        <h4>事后核对 · 不参与预警判定</h4>
        <template v-if="verification">
          <p>{{ utc(verification.point.valid_at) }} UTC · {{ position(verification.point) }}</p>
          <p>同刻距城市 <strong>{{ km(verification.distance_km) }} km</strong>；预报位置偏差 <strong>{{ km(verification.position_error_km) }} km</strong>。</p>
          <p class="case-source"><a :href="verification.source.url" target="_blank" rel="noopener noreferrer">{{ verification.source.agency }} · {{ verification.source.product }}</a></p>
        </template>
        <p v-else class="muted">没有同一有效时刻的参考点，不作替代比较。</p>
      </div>
    </div>
    <p class="muted case-limit">按球面距离比较签发后 24 小时内的离散点，不插值；未达阈值不等于全时段无风险。此规则不预测当地风雨、灾损或官方预警等级。</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  assessment: { type: Object, required: true },
  verification: { type: Object, default: null },
  showVerification: { type: Boolean, default: false }
})

const metric = computed(() => props.assessment.metric)
const closest = computed(() => props.assessment.closest_point)
const outcomeText = computed(() => ({
  NEAR: '达到教学接近阈值', NOT_NEAR: '供比较的预报点未达到阈值', INSUFFICIENT: '数据不足，无法判断'
})[props.assessment.outcome])

const caseClock = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
})
const utc = value => caseClock.format(new Date(value))
const km = value => Number(value).toFixed(1)
function position({ latitude, longitude }) {
  return `${Math.abs(latitude)}°${latitude < 0 ? 'S' : 'N'} · ${Math.abs(longitude)}°${longitude < 0 ? 'W' : 'E'}`
}
</script>

<style scoped>
.case-result {
  display: grid;
  grid-template-columns: minmax(190px, .75fr) minmax(0, 1.25fr);
  gap: 18px 24px;
  padding: 16px;
  background: var(--color-surface-soft);
  border: 1px solid var(--color-border);
  border-inline-start: 3px solid var(--color-primary);
  border-radius: var(--radius-md);
}
.case-distance { font: 700 clamp(26px, 5vw, 42px)/1.3 var(--font-mono); color: var(--color-primary); margin: 3px 0 7px; }
.case-caption, .case-limit { margin: 8px 0 0; }
.case-times { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 155px), 1fr)); gap: 10px 16px; align-content: center; }
.case-times dt { color: var(--color-text-muted); font-size: 13px; }
.case-times dd { margin: 2px 0 0; font-variant-numeric: tabular-nums; }
.case-panels { display: grid; gap: 12px; margin-top: 16px; }
.case-panels--paired { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.case-panel { min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px; }
.case-panel h4 { margin: 0 0 8px; }
.case-panel--verification { border-color: var(--color-border-strong); background: var(--color-bg); }
.case-source { margin: 8px 0 0; word-break: break-word; }
.case-source a { text-decoration: underline; }
@media (max-width: 720px) {
  .case-result, .case-panels--paired { grid-template-columns: 1fr; }
}
</style>
