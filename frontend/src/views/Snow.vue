<template>
  <div class="page">
    <header class="page-head">
      <div class="page-heading">
        <h2 class="page-title">雪灾历史回放</h2>
        <span class="page-subtitle">站点附近 · 24 小时强降雪风险 · 教学演练</span>
      </div>
      <router-link class="btn btn-ghost btn-sm" to="/hazards">查看灾种覆盖</router-link>
    </header>

    <div class="card">
      <div class="field snow-selection">
        <label class="field-label" for="snow-case">预报案例</label>
        <select id="snow-case" v-model="caseId" :disabled="catalogLoading || !cases.length || saving" @change="loadAssessment">
          <option v-for="item in cases" :key="item.case_id" :value="item.case_id">{{ item.name }}</option>
        </select>
      </div>
      <p class="muted snow-hint">切换案例可重算。预报和事后记录已离线打包，只有打开出处链接需要联网。</p>
    </div>

    <div v-if="error" class="alert alert--error" role="alert">
      {{ error }} <button type="button" class="btn btn-ghost btn-sm" @click="cases.length ? loadAssessment() : loadCatalog()">重试</button>
    </div>
    <div v-else-if="catalogLoading || loading" class="card muted" role="status">正在计算降雪风险…</div>
    <template v-else-if="result">
      <SnowEvidence :assessment="result.forecast" />
      <section class="card snow-reference" aria-label="独立事后核验">
        <header class="card-head"><h3 class="card-title">独立事后核验 · {{ result.forecast.case.city.name }}站点</h3></header>
        <template v-if="result.verification">
          <p data-testid="snow-verification">{{ result.verification.outcome === 'SNOW_REPORTED' ? '站点记录到降雪' : '抽样时次未报告降雪' }}</p>
          <p class="muted">站码只能核对天气过程，不能验证累计降雪量或证明整个窗口无雪；不会进入草稿或参与判定。</p>
          <details>
            <summary>查看 {{ result.verification.observations.length }} 条天气编码（UTC）</summary>
            <ul>
              <li v-for="row in result.verification.observations" :key="row.observed_at">
                {{ utc(row.observed_at) }} · {{ row.code }} {{ weatherLabels[row.code] }}
              </li>
            </ul>
          </details>
          <p class="muted snow-hint"><a :href="result.verification.source.url" target="_blank" rel="noopener noreferrer">{{ result.verification.source.agency }} · {{ result.verification.source.product }}</a>（{{ result.verification.station_id }}）；{{ result.verification.source.checked_on_utc }} 核对。</p>
        </template>
        <p v-else class="muted">这个窗口没有可核对的站点编码，不代表没有降雪。</p>
      </section>
    </template>

    <section v-if="canDraft" class="card" aria-label="雪灾演练草稿">
      <header class="card-head"><h3 class="card-title">创建演练草稿</h3></header>
      <p class="muted">系统只保存内置归档的预报判定。草稿不是发布，仍需提交给另一位有权限的审核员。</p>
      <button v-if="!draftOpen" class="btn btn-primary" type="button" @click="openDraft">填写雪灾演练草稿</button>
      <form v-else class="snow-draft" @submit.prevent="createDraft">
        <div class="field">
          <label class="field-label" for="snow-title">草稿标题</label>
          <input id="snow-title" v-model="draft.title" required maxlength="200" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="snow-area">研判区域</label>
          <input id="snow-area" v-model="draft.area_text" required maxlength="500" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="snow-impact">影响说明</label>
          <textarea id="snow-impact" v-model="draft.impact_text" rows="2" required maxlength="2000" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="snow-reason">研判依据</label>
          <textarea id="snow-reason" v-model="draft.reasoning_text" rows="2" required maxlength="20000" :disabled="saving" />
        </div>
        <p v-if="draftError" role="alert" class="alert alert--error">{{ draftError }}</p>
        <button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存雪灾演练草稿' }}</button>
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
import SnowEvidence from '../components/SnowEvidence.vue'

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
const weatherLabels = {
  '00': '未见云发展或无法观测', '60': '间歇性小雨', '70': '间歇性小雪', '71': '连续小雪',
  '72': '间歇性中雪', '73': '连续中雪', '74': '间歇性强降雪', '75': '连续强降雪', '79': '冰粒'
}
let active = true
let seq = 0

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
    const catalog = await apiFetch('/snow/cases')
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
  const request = ++seq
  result.value = null
  error.value = ''
  draftOpen.value = false
  draftError.value = ''
  if (!caseId.value) {
    loading.value = false
    error.value = '没有可用的历史降雪案例。'
    return
  }
  loading.value = true
  try {
    const replay = await apiFetch(`/snow/cases/${encodeURIComponent(caseId.value)}/assessment`)
    if (active && request === seq) result.value = replay
  } catch (e) {
    if (active && request === seq) error.value = e.message
  } finally {
    if (active && request === seq) loading.value = false
  }
}

function openDraft() {
  if (!canDraft.value) return
  const { case: { name, city }, metric } = result.value.forecast
  draft.title = `${name} · 雪灾演练`
  draft.area_text = `${city.name}站点附近（数值模式代表点）`
  draft.impact_text = '仅作课程案例研判，不代表现场灾损或官方预警。'
  draft.reasoning_text = `24 小时累计预报降雪 ${metric.value.toFixed(2)} cm，达到教学阈值 ≥ ${metric.threshold.toFixed(2)} cm。`
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
    const saved = await apiFetch('/warnings/snow', { method: 'POST', body: JSON.stringify(body) })
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
.snow-selection, .snow-draft { max-width: 680px; }
.snow-hint { margin-bottom: 0; }
.snow-reference summary { cursor: pointer; }
.snow-reference ul { padding-left: 1.2rem; }
</style>
