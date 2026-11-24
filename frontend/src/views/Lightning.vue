<template>
  <div class="page">
    <header class="page-head">
      <div class="page-heading">
        <h2 class="page-title">雷电历史回放</h2>
        <span class="page-subtitle">圣路易斯 KSTL 站附近 · 六小时研判 · 教学演练</span>
      </div>
      <router-link class="btn btn-ghost btn-sm" to="/hazards">查看灾种覆盖</router-link>
    </header>

    <div class="card">
      <div class="field lightning-field">
        <label class="field-label" for="lightning-case">预报窗口</label>
        <select id="lightning-case" v-model="caseId" :disabled="catalogLoading || !cases.length || saving" @change="loadAssessment">
          <option v-for="item in cases" :key="item.case_id" :value="item.case_id">{{ item.name }}</option>
        </select>
      </div>
      <p class="muted lightning-hint">切换两个归档窗口，比较同一格点的预报。预报与核验资料离线可用，打开出处链接才需要联网。</p>
    </div>

    <div v-if="error" class="alert alert--error" role="alert">
      {{ error }} <button type="button" class="btn btn-ghost btn-sm" @click="cases.length ? loadAssessment() : loadCatalog()">重试</button>
    </div>
    <div v-else-if="catalogLoading || loading" class="card muted" role="status">正在计算雷电风险…</div>
    <template v-else-if="result">
      <LightningEvidence :assessment="result.forecast" />
      <section class="card lightning-reference" aria-label="独立事后核验">
        <header class="card-head"><h3 class="card-title">独立事后核验 · {{ result.forecast.case.station_id }}</h3></header>
        <template v-if="result.verification">
          <p data-testid="lightning-verification">{{ verificationLabels[result.verification.outcome] }}</p>
          <p class="muted">抽样只核对站点附近报告的天气现象，不验证落点、逐时命中或整个窗口无雷；不参与预测与草稿计算。</p>
          <details>
            <summary>查看 {{ result.verification.observations.length }} 条站点记录（UTC）</summary>
            <ul>
              <li v-for="row in result.verification.observations" :key="row.observed_at">
                {{ utc(row.observed_at) }} · {{ row.thunder_code || '无新的雷暴天气码' }}<template v-if="row.lightning_remark"> · {{ row.lightning_remark }}（闪电备注）</template><template v-if="row.end_remark"> · {{ row.end_remark }}（上一轮雷暴结束）</template>
              </li>
            </ul>
          </details>
          <p class="muted lightning-hint"><a :href="result.verification.source.url" target="_blank" rel="noopener noreferrer">{{ result.verification.source.agency }} · {{ result.verification.source.product }}</a>；{{ result.verification.source.checked_on_utc }} 核对。</p>
        </template>
        <p v-else class="muted">该窗没有可用的站点核验资料，不代表没有雷暴或闪电。</p>
      </section>
    </template>

    <section v-if="canDraft" class="card" aria-label="雷电演练草稿">
      <header class="card-head"><h3 class="card-title">创建演练草稿</h3></header>
      <p class="muted">系统只保存服务器重算的归档预报判定。草稿未发布，需交另一位有权限的审核员复核。</p>
      <button v-if="!draftOpen" class="btn btn-primary" type="button" @click="openDraft">填写雷电演练草稿</button>
      <form v-else class="lightning-field" @submit.prevent="createDraft">
        <div class="field">
          <label class="field-label" for="lightning-title">草稿标题</label>
          <input id="lightning-title" v-model="draft.title" required maxlength="200" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="lightning-area">研判区域</label>
          <input id="lightning-area" v-model="draft.area_text" required maxlength="500" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="lightning-impact">影响说明</label>
          <textarea id="lightning-impact" v-model="draft.impact_text" rows="2" required maxlength="2000" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="lightning-reason">研判依据</label>
          <textarea id="lightning-reason" v-model="draft.reasoning_text" rows="2" required maxlength="20000" :disabled="saving" />
        </div>
        <p v-if="draftError" role="alert" class="alert alert--error">{{ draftError }}</p>
        <button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存雷电演练草稿' }}</button>
        <button class="btn btn-ghost" type="button" :disabled="saving" @click="draftOpen = false">放弃</button>
      </form>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api'
import { auth } from '../auth'
import LightningEvidence from '../components/LightningEvidence.vue'

const router = useRouter()
const cases = ref([])
const caseId = ref('')
const result = ref(null)
const catalogLoading = ref(true)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const draftError = ref('')
const draftOpen = ref(false)
const draft = reactive({ title: '', area_text: '', impact_text: '', reasoning_text: '' })
const verificationLabels = {
  THUNDER_AND_LIGHTNING_REPORTED: '站点报告雷暴及闪电备注',
  THUNDER_REPORTED: '站点报告雷暴，未提取到闪电备注',
  LIGHTNING_REPORTED: '站点有闪电备注，未提取到雷暴天气码',
  NO_EVENT_IN_SAMPLES: '抽样时次未报告新的雷暴或闪电'
}
let active = true
let sequence = 0

const canDraft = computed(() => {
  const forecast = result.value?.forecast
  return auth.hasAnyRole('ANALYST', 'ADMIN') && !loading.value && forecast?.outcome === 'REACHED' &&
    Boolean(forecast.metric && forecast.case.archive_latest_modified_at) && forecast.case.case_id === caseId.value
})

function utc(value) {
  return new Date(value).toISOString().slice(0, 16).replace('T', ' ')
}

async function loadCatalog() {
  catalogLoading.value = true
  error.value = ''
  try {
    const catalog = await apiFetch('/lightning/cases')
    if (!active) return
    cases.value = catalog.cases
    caseId.value = cases.value[0]?.case_id || ''
    await loadAssessment()
  } catch (e) {
    if (active) error.value = e.message
  } finally {
    if (active) catalogLoading.value = false
  }
}

async function loadAssessment() {
  const request = ++sequence
  result.value = null
  error.value = ''
  draftOpen.value = false
  draftError.value = ''
  if (!caseId.value) {
    loading.value = false
    error.value = '没有可用的雷电历史案例。'
    return
  }
  loading.value = true
  try {
    const replay = await apiFetch(`/lightning/cases/${encodeURIComponent(caseId.value)}/assessment`)
    if (active && request === sequence) result.value = replay
  } catch (e) {
    if (active && request === sequence) error.value = e.message
  } finally {
    if (active && request === sequence) loading.value = false
  }
}

function openDraft() {
  if (!canDraft.value) return
  const { case: { name, city, station_id }, metric } = result.value.forecast
  draft.title = `${name} · 雷电演练`
  draft.area_text = `${city.name} ${station_id} 站附近（数值模式代表点）`
  draft.impact_text = '仅作课程案例研判，不代表实际落雷、灾损或官方预警。'
  draft.reasoning_text = `六个有效时次齐全，最大 LTNG ${metric.value}（无量纲），达到教学界线 ≥ ${metric.threshold}。`
  draftOpen.value = true
  draftError.value = ''
}

async function createDraft() {
  if (!canDraft.value || saving.value || !draftOpen.value) return
  const body = { case_id: caseId.value }
  for (const key of Object.keys(draft)) {
    body[key] = draft[key].trim()
    if (!body[key]) {
      draftError.value = '请填写标题、研判区域、影响说明和研判依据。'
      return
    }
  }
  saving.value = true
  draftError.value = ''
  try {
    const saved = await apiFetch('/warnings/lightning', { method: 'POST', body: JSON.stringify(body) })
    if (active) await router.push(`/warnings/${saved.public_id}`)
  } catch (e) {
    if (active) draftError.value = e.message
  } finally {
    if (active) saving.value = false
  }
}

onMounted(loadCatalog)
onUnmounted(() => { active = false })
</script>

<style scoped>
.lightning-field { max-width: 680px; }
.lightning-hint { margin-bottom: 0; overflow-wrap: anywhere; }
.lightning-reference summary { cursor: pointer; }
.lightning-reference ul { padding-left: 1.2rem; }
</style>
