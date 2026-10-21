<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">灾种覆盖</h2>
        <span class="page-subtitle">
          共 {{ summary.total }} 类场景 · {{ summary.implemented }} 类端到端实现 · {{ summary.framework }} 类扩展框架
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
            :class="h.status === 'IMPLEMENTED' ? 'badge--success' : 'badge--neutral'"
            style="margin-left: auto"
          >
            {{ h.status === 'IMPLEMENTED' ? '端到端实现' : '扩展框架' }}
          </span>
        </div>
        <div class="mono muted" style="margin-bottom: 10px">{{ h.code }}</div>

        <div class="hazard-row">
          <span class="detail-label">判定指标</span>
          <span class="detail-value">{{ h.indicator }}（{{ h.unit }}）</span>
        </div>

        <div class="hazard-row">
          <span class="detail-label">阈值</span>
          <span class="badge-group">
            <span
              v-for="t in h.thresholds"
              :key="t.code"
              class="badge badge--sm badge--info"
            >
              {{ t.label }} {{ t.value }}{{ h.unit }}
            </span>
          </span>
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
      </div>
    </div>

    <div v-if="!loading && hazards.length" class="card">
      <h3 class="card-title" style="margin-bottom: 8px">交付边界说明</h3>
      <p class="muted" style="margin-bottom: 6px">
        选题要求覆盖八类场景。当前交付采用「1 类端到端 + 7 类扩展框架」口径：暴雨已完成数据接入、
        四模式融合、量化对比与完整发布闭环；其余七类复用同一套预警状态机、角色权限、审批发布与审计结构，
        数据源与判定指标已登记，但尚未接入数据、也不承诺同等的量化验证。
      </p>
      <p class="muted" style="margin: 0">
        答辩时按此边界说明，不把扩展设计表述为已完成验证。
      </p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import EmptyState from '../components/EmptyState.vue'

const hazards = ref([])
const summary = ref({ total: 8, implemented: 0, framework: 0 })
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
  border-color: #a7f3d0;
  box-shadow: 0 10px 28px -20px rgb(5 150 105 / 0.5);
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
  color: #475569;
}

.hazard-list li {
  margin: 1px 0;
}

.hazard-note {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px dashed #e2e8f0;
}
</style>
