<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">总览</h2>
        <span class="page-subtitle">多源降水融合与预警运营概览</span>
      </div>
    </div>

    <Transition name="slide-fade">
      <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
        <span class="alert-icon" aria-hidden="true">!</span>
        <div>{{ error }}</div>
      </div>
    </Transition>

    <div class="stat-grid stat-grid--4 stagger">
      <div class="stat-card">
        <span class="stat-icon stat-icon--blue" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 20V9l8-5 8 5v11" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
            <path d="M9 20v-6h6v6" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
          </svg>
        </span>
        <div>
          <div class="stat-value">{{ cityDisplay }}</div>
          <div class="stat-label">接入城市</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon stat-icon--orange" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 19V5M4 19h16" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            <path d="m7 15 4-5 3 3 5-7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <div>
          <div class="stat-value">{{ f1Display }}</div>
          <div class="stat-label">融合 F1（10mm/24h）</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon stat-icon--red" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 3 2.8 19h18.4L12 3Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
            <path d="M12 9v5M12 17h.01" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
          </svg>
        </span>
        <div>
          <div class="stat-value">{{ warningDisplay }}</div>
          <div class="stat-label">预警记录</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon stat-icon--yellow" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M6 18h12M7 15a5 5 0 1 1 10 0c0 2 1 3 1 3H6s1-1 1-3Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
            <path d="M10 21h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
          </svg>
        </span>
        <div>
          <div class="stat-signals">
            <span class="signal-pill signal-pill--blue">蓝 {{ signalCounts.BLUE }}</span>
            <span class="signal-pill signal-pill--yellow">黄 {{ signalCounts.YELLOW }}</span>
            <span class="signal-pill signal-pill--orange">橙 {{ signalCounts.ORANGE }}</span>
          </div>
          <div class="stat-label">信号分布</div>
        </div>
      </div>
    </div>

    <div class="chart-grid">
      <ChartPanel
        title="城市态势"
        subtitle="九城预警分布 · 颜色为最高信号"
        :option="mapOption"
        :height="416"
        aria-label="中国地图，九城预警分布"
        sweep
      />
      <div class="chart-stack">
        <ChartPanel
          title="指标对比"
          subtitle="基线 ECMWF vs 四模式融合"
          :option="radarOption"
          :height="200"
          aria-label="基线与融合模型指标雷达图"
        />
        <ChartPanel
          title="预警状态分布"
          subtitle="按当前状态计数"
          :option="statusOption"
          :height="200"
          aria-label="预警状态分布条形图"
        />
      </div>
    </div>

    <div class="chart-grid">
      <div class="card" style="margin-bottom: 0">
        <div class="card-head">
          <h3 class="card-title">量化提升（冻结指标）</h3>
          <span class="card-subtitle">九城合并 · 测试年 2026 · 10mm/24h</span>
        </div>
        <div v-if="metrics" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th scope="col">指标</th><th scope="col">基线 ECMWF</th><th scope="col">四模式融合</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>F1</td>
                <td>{{ fmt(metrics.baseline.f1) }}</td>
                <td class="cell-accent success">{{ fmt(metrics.fusion.f1) }}（{{ signed(metrics.delta_f1) }} 点）</td>
              </tr>
              <tr>
                <td>误报率</td>
                <td>{{ pct(metrics.baseline.fpr) }}</td>
                <td class="cell-accent success">{{ pct(metrics.fusion.fpr) }}</td>
              </tr>
              <tr>
                <td>AUC</td>
                <td>{{ fmt(metrics.baseline.auc) }}</td>
                <td class="cell-accent">{{ fmt(metrics.fusion.auc) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="metrics" class="muted" style="margin-top: 12px">
          自举 95% 区间 [{{ signed(metrics.bootstrap_interval[0]) }}, {{ signed(metrics.bootstrap_interval[1]) }}]，
          P(提升)={{ metrics.p_improve }}。标签为 ERA5 代理标签，非站点实测。
        </p>
        <router-link to="/metrics">查看完整指标 →</router-link>
      </div>

      <ChartPanel
        title="最近预警 · 四模式输入"
        :subtitle="latestTitle || '取最新一条预警的融合输入'"
        :option="modelOption"
        :height="248"
        empty-text="暂无预警，创建后展示四模式对比"
        aria-label="最近预警的四模式降水柱状图"
      />
    </div>

    <div class="card stagger">
      <div class="card-head">
        <h3 class="card-title">最近预警</h3>
        <span class="card-subtitle">按创建顺序展示最近 10 条</span>
      </div>

      <TableSkeleton v-if="loading" :rows="4" :cols="4" />

      <EmptyState
        v-else-if="!warnings.length"
        title="暂无预警记录"
        description="分析员创建草稿后，这里会显示最近动态。"
        compact
      />

      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr><th scope="col">标题</th><th scope="col">城市</th><th scope="col">状态</th><th scope="col">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="w in warnings" :key="w.public_id">
              <td class="cell-primary">{{ w.title }}</td>
              <td>{{ cityName(w.city_code) }}</td>
              <td><StatusBadge :value="w.status" size="sm" dot /></td>
              <td>
                <router-link class="btn btn-ghost btn-sm" :to="'/warnings/' + w.public_id">查看</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import ChartPanel from '../components/ChartPanel.vue'
import { useCountUp } from '../ui/useCountUp'
import { CITY_COORDS } from '../data/cityCoords'
import { baselineRadar, chinaMap, modelBar, statusBar } from '../charts/options'

const RISK_RANK = { BLUE: 1, YELLOW: 2, ORANGE: 3, RED: 4 }

const cityCount = ref(0)
const warningCount = ref(0)
const f1Value = ref(null)
const cities = ref([])
const allWarnings = ref([])
const metrics = ref(null)
const loading = ref(true)
const error = ref('')

const latestModels = ref([])
const latestBaseline = ref(null)
const latestProxy = ref(null)
const latestTitle = ref('')

const cityDisplay = useCountUp(cityCount)
const warningDisplay = useCountUp(warningCount)
const f1Display = useCountUp(f1Value, { decimals: 4 })

const warnings = computed(() => allWarnings.value.slice(0, 10))

const signalCounts = computed(() => {
  const counts = { BLUE: 0, YELLOW: 0, ORANGE: 0, RED: 0 }
  for (const w of allWarnings.value) {
    if (counts[w.risk_level] != null) counts[w.risk_level] += 1
  }
  return counts
})

const statusCounts = computed(() => {
  const counts = {}
  for (const w of allWarnings.value) {
    counts[w.status] = (counts[w.status] || 0) + 1
  }
  return counts
})

const mapOption = computed(() => {
  if (!cities.value.length) return null
  const byCity = {}
  for (const city of cities.value) {
    const coord = CITY_COORDS[city.code]
    if (!coord) continue
    byCity[city.code] = {
      name: city.name,
      lon: coord[0],
      lat: coord[1],
      count: 0,
      risk: null
    }
  }
  for (const w of allWarnings.value) {
    const point = byCity[w.city_code]
    if (!point) continue
    point.count += 1
    if ((RISK_RANK[w.risk_level] || 0) > (RISK_RANK[point.risk] || 0)) {
      point.risk = w.risk_level
    }
  }
  return chinaMap(Object.values(byCity))
})

const radarOption = computed(() =>
  metrics.value ? baselineRadar(metrics.value.baseline, metrics.value.fusion) : null
)

const statusOption = computed(() =>
  allWarnings.value.length ? statusBar(statusCounts.value) : null
)

const modelOption = computed(() =>
  latestModels.value.length
    ? modelBar(latestModels.value, {
        baseline: latestBaseline.value,
        proxy: latestProxy.value
      })
    : null
)

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
}

function fmt(value, digits = 4) {
  return value == null ? '—' : Number(value).toFixed(digits)
}

function pct(value) {
  return value == null ? '—' : `${(Number(value) * 100).toFixed(2)}%`
}

function signed(value) {
  if (value == null) return '—'
  const n = Number(value)
  return n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2)
}

onMounted(async () => {
  const [citiesResult, metricsResult, detailResult, warningsResult] = await Promise.allSettled([
    apiFetch('/cities'),
    apiFetch('/metrics/experiments'),
    apiFetch('/metrics/experiments/10mm'),
    apiFetch('/warnings')
  ])

  const failed = []

  if (citiesResult.status === 'fulfilled') {
    cities.value = citiesResult.value
    cityCount.value = citiesResult.value.length
  } else {
    failed.push('城市列表')
  }

  if (detailResult.status === 'fulfilled') {
    metrics.value = detailResult.value
    f1Value.value = detailResult.value.fusion.f1
  } else {
    failed.push('指标数据')
  }

  if (metricsResult.status === 'rejected') {
    failed.push('实验列表')
  }

  if (warningsResult.status === 'fulfilled') {
    allWarnings.value = warningsResult.value
    warningCount.value = warningsResult.value.length
  } else {
    failed.push('预警列表')
  }

  if (failed.length) {
    error.value = `部分数据加载失败：${failed.join('、')}，请稍后刷新。`
  }

  loading.value = false

  if (allWarnings.value.length) {
    try {
      const detail = await apiFetch(`/warnings/${allWarnings.value[0].public_id}`)
      latestModels.value = detail.models || []
      latestBaseline.value = detail.baseline_mm
      latestProxy.value = detail.proxy_label_mm
      latestTitle.value = detail.title
    } catch (e) {
      latestModels.value = []
    }
  }
})
</script>
