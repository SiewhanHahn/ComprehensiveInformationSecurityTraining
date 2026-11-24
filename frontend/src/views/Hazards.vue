<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">灾种覆盖</h2>
        <span class="page-subtitle">
          共 {{ summary.total }} 类场景 · {{ summary.implemented }} 类端到端实现 · {{ summary.basic }} 类基础预测 · {{ summary.framework }} 类待实现
        </span>
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

    <div v-if="loading" class="grid grid-3">
      <div v-for="i in 6" :key="i" class="card">
        <div class="skeleton skeleton-line" style="width: 45%; height: 18px"></div>
        <div class="skeleton skeleton-line" style="width: 80%"></div>
        <div class="skeleton skeleton-line" style="height: 70px"></div>
      </div>
    </div>

    <EmptyState v-else-if="!hazards.length" title="暂无灾种数据" description="请稍后刷新重试。" />

    <div v-else class="grid grid-3 stagger">
      <div
        v-for="h in hazards"
        :key="h.code"
        class="card card--hover"
        :class="{ 'hazard-card--implemented': h.status === 'IMPLEMENTED' }"
      >
        <div class="card-head" style="align-items: center; margin-bottom: 8px">
          <h3 class="card-title">{{ h.name }}</h3>
          <span
            class="badge"
            :class="statusLabels[h.status]?.color || 'badge--neutral'"
            style="margin-left: auto"
          >
            {{ statusLabels[h.status]?.text || '待实现' }}
          </span>
        </div>
        <div class="mono muted" style="margin-bottom: 10px">{{ h.code }}</div>

        <div class="hazard-row">
          <span class="detail-label">判定指标</span>
          <span class="detail-value">{{ h.indicator }}（{{ h.unit }}）</span>
        </div>

        <div class="hazard-row">
          <span class="detail-label">阈值</span>
          <span v-if="h.thresholds.length" class="badge-group">
            <span
              v-for="t in h.thresholds"
              :key="t.code"
              class="badge badge--sm badge--info"
            >
              {{ t.label }} {{ t.value }}{{ h.unit }}
            </span>
          </span>
          <span v-else class="muted">待定，尚未用于预测</span>
        </div>

        <div class="hazard-row">
          <span class="detail-label">数据源</span>
          <ul class="hazard-list">
            <li v-for="s in h.data_sources" :key="s">{{ s }}</li>
          </ul>
        </div>

        <div class="hazard-row">
          <span class="detail-label">判定方法</span>
          <span class="detail-value">{{ h.judgement }}</span>
        </div>

        <p class="muted hazard-note">{{ h.note }}</p>
        <router-link v-if="h.code === 'TYPHOON' && h.status === 'IMPLEMENTED'" class="btn btn-ghost btn-sm" to="/typhoon">查看台风历史案例</router-link>
        <router-link v-if="h.code === 'SNOW_DISASTER' && h.status === 'IMPLEMENTED'" class="btn btn-ghost btn-sm" to="/snow">查看雪灾历史案例</router-link>
        <router-link v-if="h.code === 'THUNDERSTORM' && h.status === 'IMPLEMENTED'" class="btn btn-ghost btn-sm" to="/lightning">查看雷电历史案例</router-link>
        <router-link v-if="h.code === 'DROUGHT' && h.status === 'BASIC'" class="btn btn-ghost btn-sm" to="/basic-forecast">试算干旱风险</router-link>
        <router-link v-if="h.code === 'HEATWAVE' && h.status === 'BASIC'" class="btn btn-ghost btn-sm" to="/basic-forecast?hazard=heat">试算高温风险</router-link>
      </div>
    </div>

    <div v-if="!loading && hazards.length" class="card">
      <h3 class="card-title" style="margin-bottom: 8px">交付边界说明</h3>
      <p class="muted" style="margin-bottom: 6px">
        终期要求四类重点运行（暴雨、台风、雪灾、雷电），四类基本预测（干旱、高温、低温、风雹）。
        当前有暴雨、台风、雪灾和雷电的研判与预警流程。暴雨展示九城统计对照，另三类只做历史案例核对。
      </p>
      <p class="muted" style="margin: 0">
        干旱可输入数据做基础试算，不生成预警；待实现项不生成预测结果。这不是八灾种终验。
      </p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import EmptyState from '../components/EmptyState.vue'

const hazards = ref([])
const summary = ref({ total: 8, implemented: 0, basic: 0, framework: 0 })
const statusLabels = {
  IMPLEMENTED: { text: '端到端实现', color: 'badge--success' },
  BASIC: { text: '基础预测', color: 'badge--info' }
}
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch('/hazards')
    hazards.value = data.hazards || []
    if (data.summary) summary.value = data.summary
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hazard-card--implemented {
  border-color: var(--success-border);
  box-shadow: none;
}

.hazard-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 10px;
}

.hazard-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.hazard-list li {
  margin: 1px 0;
}

.hazard-note {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border);
}
</style>
