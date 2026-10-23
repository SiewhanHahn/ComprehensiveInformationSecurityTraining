<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">数据监测</h2>
        <span class="page-subtitle">
          数据源、数据集与覆盖状态 · 最近更新 {{ formatDateTime(status?.generated_at) }}
        </span>
      </div>
      <div class="page-actions">
        <span class="badge badge--warning">历史快照，非实时接入</span>
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner spinner--dark"></span>
          刷新
        </button>
      </div>
    </div>

    <Transition name="slide-fade">
      <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
        <span class="alert-icon" aria-hidden="true">!</span>
        <div>
          {{ error }}
          <button class="btn btn-ghost btn-sm" type="button" @click="load">重新加载</button>
        </div>
      </div>
    </Transition>

    <div v-if="loading && !status" class="card">
      <div class="skeleton skeleton-line" style="width: 40%; height: 18px"></div>
      <div class="skeleton skeleton-line" style="height: 160px; margin-top: 16px"></div>
    </div>

    <template v-else-if="status">
      <div class="stat-grid stagger">
        <div class="stat-card">
          <span class="stat-icon stat-icon--blue" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 6h16M4 12h16M4 18h10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            </svg>
          </span>
          <div>
            <div class="stat-value">{{ forecastDisplay }}</div>
            <div class="stat-label">预报记录</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-icon stat-icon--violet" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M5 19V9m7 10V5m7 14v-7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            </svg>
          </span>
          <div>
            <div class="stat-value">{{ observationDisplay }}</div>
            <div class="stat-label">代理标签记录</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-icon stat-icon--amber" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 3v18M3 12h18" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
              <circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.7" />
            </svg>
          </span>
          <div>
            <div class="stat-value">{{ coverage.models.length }}</div>
            <div class="stat-label">已接入模式 / 预期 {{ coverage.expected_models.length }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h3 class="card-title">覆盖完整性</h3>
          <span class="card-subtitle">基于回放口径的模型齐全度汇总</span>
          <span style="margin-left: auto">
            <StatusBadge kind="dataStatus" :value="coverage.completeness" />
          </span>
        </div>
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-value">{{ formatDate(status.records.latest_observed_date) }}</div>
            <div class="summary-label">最新代理标签日期</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">{{ formatDateTime(status.records.latest_forecast_valid_at) }}</div>
            <div class="summary-label">最新预报有效时刻（北京时间）</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">{{ coverage.cities.length }}</div>
            <div class="summary-label">覆盖城市</div>
          </div>
        </div>
        <div class="row" style="gap: 6px">
          <span class="detail-label" style="margin: 0 4px 0 0">模式：</span>
          <span
            v-for="m in coverage.models"
            :key="m"
            class="badge badge--sm"
            :class="coverage.expected_models.includes(m) ? 'badge--success' : 'badge--neutral'"
          >
            {{ modelLabel(m) }}
          </span>
        </div>
        <p v-if="coverage.partial_days > 0" class="muted" style="margin: 12px 0 0">
          当前有 <strong>{{ coverage.partial_days }}</strong> 个城日缺少部分模式数据（如某日缺某模式），
          该城日回放会标记为「数据不完整」，不影响其余完整样本的融合与预警。
        </p>
        <p v-if="coverage.dataset_version" class="muted" style="margin: 6px 0 0">
          统计口径数据集版本：<span class="mono">{{ coverage.dataset_version }}</span>
        </p>
      </div>

      <div class="card">
        <div class="card-head">
          <h3 class="card-title">数据源</h3>
          <span class="card-subtitle">共 {{ status.sources.length }} 个</span>
        </div>
        <EmptyState v-if="!status.sources.length" title="暂无数据源" compact />
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr><th scope="col">名称</th><th scope="col">类型</th><th scope="col">许可说明</th><th scope="col">状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in status.sources" :key="s.code">
                <td class="cell-primary">{{ s.name }}</td>
                <td>{{ sourceTypeLabel(s.data_type) }}</td>
                <td class="cell-wrap muted">{{ s.license_note || '—' }}</td>
                <td>
                  <span class="badge badge--sm" :class="s.is_active ? 'badge--success' : 'badge--neutral'">
                    {{ s.is_active ? '启用' : '停用' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h3 class="card-title">数据集</h3>
          <span class="card-subtitle">共 {{ status.datasets.length }} 个 · 导入时间按北京时间显示</span>
        </div>
        <EmptyState v-if="!status.datasets.length" title="暂无数据集" compact />
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th scope="col">类型</th>
                <th scope="col">版本</th>
                <th scope="col">时间范围</th>
                <th scope="col">记录数</th>
                <th scope="col">质量状态</th>
                <th scope="col">导入时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in status.datasets" :key="d.id">
                <td class="cell-primary">{{ datasetTypeLabel(d.dataset_type) }}</td>
                <td class="mono">{{ d.version }}</td>
                <td class="cell-nowrap">{{ d.period_start }} ~ {{ d.period_end }}</td>
                <td>{{ d.row_count }}</td>
                <td>
                  <span class="badge badge--sm" :class="d.quality_status === 'READY' ? 'badge--success' : 'badge--warning'">
                    {{ d.quality_status }}
                  </span>
                </td>
                <td class="cell-nowrap">{{ formatDateTime(d.imported_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <p class="muted" style="margin: 0">
          本页展示的是已导入的历史数据快照，不表示系统正在实时接收外部数据。
          外部数据服务不可用时，回放与指标仍基于本地缓存运行；数据来源与导入时间在此可见。
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import { useCountUp } from '../ui/useCountUp'
import { datasetTypeLabel, formatDate, formatDateTime, modelLabel, sourceTypeLabel } from '../ui/labels'

const status = ref(null)
const loading = ref(true)
const error = ref('')

const forecastCount = ref(0)
const observationCount = ref(0)
const forecastDisplay = useCountUp(forecastCount)
const observationDisplay = useCountUp(observationCount)

const coverage = computed(
  () => status.value?.coverage || { models: [], expected_models: [], cities: [], per_city: [], partial_days: 0, dataset_version: null, completeness: 'PARTIAL' }
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await apiFetch('/monitor/status')
    forecastCount.value = status.value.records.forecast
    observationCount.value = status.value.records.observation
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
