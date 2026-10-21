<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">历史回放</h2>
        <span class="page-subtitle">固定 24 小时提前量 · 四模式与等权融合</span>
      </div>
    </div>

    <div class="card">
      <form @submit.prevent="load">
        <div class="form-row">
          <div class="field" style="flex: 1; min-width: 160px">
            <label class="field-label" for="r-city">城市</label>
            <select id="r-city" v-model="city">
              <option v-for="c in cities" :key="c.code" :value="c.code">{{ c.name }}</option>
            </select>
          </div>
          <div class="field" style="flex: 1; min-width: 160px">
            <label class="field-label" for="r-date">日期（UTC）</label>
            <input id="r-date" v-model="date" type="date" />
          </div>
          <div class="field" style="flex: 1; min-width: 180px">
            <label class="field-label" for="r-threshold">阈值</label>
            <select id="r-threshold" v-model="threshold">
              <option value="MODERATE">10mm/24h（中雨）</option>
              <option value="HEAVY">25mm/24h（大雨）</option>
              <option value="STORM">50mm/24h（暴雨）</option>
            </select>
          </div>
          <div class="field">
            <button class="btn btn-primary" type="submit" :disabled="loading">
              <span v-if="loading" class="spinner"></span>
              {{ loading ? '回放中…' : '回放' }}
            </button>
          </div>
        </div>
      </form>

      <Transition name="slide-fade">
        <div v-if="error" class="alert alert--error" role="alert" style="margin-top: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>{{ error }}</div>
        </div>
      </Transition>
    </div>

    <div v-if="loading" class="card">
      <div class="skeleton skeleton-line" style="width: 45%; height: 18px"></div>
      <div class="skeleton skeleton-line" style="height: 160px; margin-top: 16px"></div>
    </div>

    <Transition name="rise">
      <div v-if="result && !loading" class="card">
        <div class="card-head">
          <h3 class="card-title">回放结果</h3>
          <span class="card-subtitle">
            {{ result.city.name }} · {{ result.valid_date }}
          </span>
          <span style="margin-left: auto">
            <StatusBadge kind="dataStatus" :value="result.data_status" />
          </span>
        </div>

        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr><th scope="col">模式</th><th scope="col">24h 累计降水 (mm)</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in result.models" :key="m.model">
                <td class="cell-primary">{{ m.model }}</td>
                <td>{{ m.precipitation_mm == null ? '缺测' : m.precipitation_mm }}</td>
              </tr>
              <tr>
                <td class="cell-primary">等权融合</td>
                <td class="cell-accent">{{ result.fused_mm == null ? '数据不完整' : result.fused_mm }}</td>
              </tr>
              <tr>
                <td class="cell-primary">ECMWF 基线</td>
                <td>{{ result.baseline_mm ?? '—' }}</td>
              </tr>
              <tr>
                <td class="cell-primary">ERA5 代理标签</td>
                <td>{{ result.proxy_label_mm ?? '—' }} <span class="muted">（再分析，非站点实测）</span></td>
              </tr>
              <tr>
                <td class="cell-primary">教学风险等级</td>
                <td><StatusBadge kind="risk" :value="result.risk_level" /></td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="muted" style="margin-top: 12px">
          缺任一模式时显示 PARTIAL，不生成正式预警；教学风险等级不代表国家气象台官方预警信号。
        </p>

        <div v-if="auth.hasAnyRole('ANALYST', 'ADMIN') && result.data_status === 'COMPLETE'" style="margin-top: 12px">
          <router-link
            class="btn btn-secondary btn-sm"
            :to="{ path: '/warnings', query: { city: result.city.code, date: result.valid_date, threshold: threshold } }"
          >
            基于此回放创建预警 →
          </router-link>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import { auth } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'

const cities = ref([])
const city = ref('CHANGSHA')
const date = ref('2024-03-27')
const threshold = ref('HEAVY')
const result = ref(null)
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    cities.value = await apiFetch('/cities')
  } catch (e) {
    error.value = e.message
  }
})

async function load() {
  error.value = ''
  result.value = null
  loading.value = true
  try {
    result.value = await apiFetch(
      `/replay?city_code=${city.value}&date=${date.value}&threshold_code=${threshold.value}`
    )
  } catch (e) {
    error.value = e.message || '该城市/日期无样本数据'
  } finally {
    loading.value = false
  }
}
</script>
