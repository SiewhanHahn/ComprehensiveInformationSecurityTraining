<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">指标对比</h2>
        <span class="page-subtitle">基线 ECMWF 与四模式等权融合</span>
      </div>
    </div>

    <div class="card">
      <div class="field" style="max-width: 420px">
        <label class="field-label" for="m-version">实验版本</label>
        <select id="m-version" v-model="version" @change="loadDetail">
          <option v-for="e in experiments" :key="e.version" :value="e.version">
            {{ e.version }} /24h（n={{ e.n }}）
          </option>
        </select>
      </div>
    </div>

    <Transition name="slide-fade">
      <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
        <span class="alert-icon" aria-hidden="true">!</span>
        <div>
          {{ error }}
          <button class="btn btn-ghost btn-sm" type="button" @click="loadDetail">重新加载</button>
        </div>
      </div>
    </Transition>

    <div v-if="loading" class="card">
      <div class="skeleton skeleton-line" style="width: 40%; height: 18px"></div>
      <div class="skeleton skeleton-line" style="width: 70%"></div>
      <div class="skeleton skeleton-line" style="height: 140px; margin-top: 16px"></div>
    </div>

    <div v-else-if="detail" class="card">
      <div class="card-head">
        <h3 class="card-title">{{ detail.version }} /24h</h3>
        <span class="card-subtitle">测试年 {{ detail.test_years.join(', ') }} · 九城合并 n={{ detail.n }} · 正类 {{ detail.positives }}</span>
      </div>
      <p class="muted">{{ detail.label_note }}</p>

      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-value success">{{ (detail.delta_f1 >= 0 ? '+' : '') + detail.delta_f1 }}</div>
          <div class="summary-label">ΔF1（百分点）</div>
        </div>
        <div class="summary-item">
          <div class="summary-value">[{{ detail.bootstrap_interval[0] }}, {{ detail.bootstrap_interval[1] }}]</div>
          <div class="summary-label">自举 95% 区间</div>
        </div>
        <div class="summary-item">
          <div class="summary-value">{{ detail.p_improve }}</div>
          <div class="summary-label">P(提升)</div>
        </div>
      </div>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th scope="col">指标</th><th scope="col">基线 ECMWF</th><th scope="col">四模式融合</th></tr>
          </thead>
          <tbody>
            <tr><td>精确率</td><td>{{ detail.baseline.precision }}</td><td class="cell-accent">{{ detail.fusion.precision }}</td></tr>
            <tr><td>召回率</td><td>{{ detail.baseline.recall }}</td><td class="cell-accent">{{ detail.fusion.recall }}</td></tr>
            <tr><td>误报率</td><td>{{ detail.baseline.fpr }}</td><td class="cell-accent">{{ detail.fusion.fpr }}</td></tr>
            <tr><td>F1</td><td>{{ detail.baseline.f1 }}</td><td class="cell-accent success">{{ detail.fusion.f1 }}</td></tr>
            <tr><td>AUC</td><td>{{ detail.baseline.auc }}</td><td class="cell-accent">{{ detail.fusion.auc }}</td></tr>
          </tbody>
        </table>
      </div>

      <p v-if="detail.threshold_mm === 25" class="muted" style="margin-top: 12px">
        25mm 为探索性结果：融合召回率下降、精确率上升，不声称所有等级均提升。
      </p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'

const experiments = ref([])
const version = ref('10mm')
const detail = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    experiments.value = await apiFetch('/metrics/experiments')
    if (experiments.value.length) version.value = experiments.value[0].version
    await loadDetail()
  } catch (e) {
    error.value = e.message
    loading.value = false
  }
})

async function loadDetail() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await apiFetch(`/metrics/experiments/${version.value}`)
  } catch (e) {
    detail.value = null
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
