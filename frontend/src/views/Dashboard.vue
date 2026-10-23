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

    <div class="stat-grid stagger">
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
        <span class="stat-icon stat-icon--violet" aria-hidden="true">
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
        <span class="stat-icon stat-icon--amber" aria-hidden="true">
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
    </div>

    <div class="card stagger">
      <div class="card-head">
        <h3 class="card-title">量化提升（冻结指标）</h3>
        <span class="card-subtitle">九城合并 · 测试年 2026 · n=2403 · 10mm/24h</span>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th scope="col">指标</th><th scope="col">基线 ECMWF</th><th scope="col">四模式融合</th></tr>
          </thead>
          <tbody>
            <tr><td>F1</td><td>0.7462</td><td class="cell-accent success">0.7900（+4.38 点）</td></tr>
            <tr><td>误报率</td><td>6.51%</td><td class="cell-accent success">5.21%</td></tr>
            <tr><td>AUC</td><td>0.9586</td><td class="cell-accent">0.9720</td></tr>
          </tbody>
        </table>
      </div>
      <p class="muted" style="margin-top: 12px">
        自举 95% 区间 [+1.57, +7.29]，P(提升)=0.998。标签为 ERA5 代理标签，非站点实测。
      </p>
      <router-link to="/metrics">查看完整指标 →</router-link>
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
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { useCountUp } from '../ui/useCountUp'

const cityCount = ref(0)
const warningCount = ref(0)
const f1Value = ref(null)
const cities = ref([])
const warnings = ref([])
const loading = ref(true)
const error = ref('')

const cityDisplay = useCountUp(cityCount)
const warningDisplay = useCountUp(warningCount)
const f1Display = useCountUp(f1Value, { decimals: 4 })

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
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
    f1Value.value = detailResult.value.fusion.f1
  } else {
    failed.push('指标数据')
  }

  if (metricsResult.status === 'rejected') {
    failed.push('实验列表')
  }

  if (warningsResult.status === 'fulfilled') {
    warnings.value = warningsResult.value.slice(0, 10)
    warningCount.value = warningsResult.value.length
  } else {
    failed.push('预警列表')
  }

  if (failed.length) {
    error.value = `部分数据加载失败：${failed.join('、')}，请稍后刷新。`
  }

  loading.value = false
})
</script>
