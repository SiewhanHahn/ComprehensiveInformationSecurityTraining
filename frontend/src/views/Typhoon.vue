<template>
  <div class="page">
    <header class="page-head">
      <div class="page-heading">
        <h2 class="page-title">台风路径回放</h2>
        <span class="page-subtitle">历史航运公报 · 城市接近判定 · 教学演练</span>
      </div>
      <router-link class="btn btn-ghost btn-sm" to="/replay">返回降水回放</router-link>
    </header>

    <div class="card">
      <div class="typhoon-fields">
        <div class="field">
          <label class="field-label" for="typhoon-case">历史台风</label>
          <select id="typhoon-case" v-model="caseId" :disabled="catalogLoading || !cases.length || saving" @change="loadAssessment">
            <option v-for="item in cases" :key="item.case_id" :value="item.case_id">{{ item.name }}（{{ item.storm_number }}）</option>
          </select>
        </div>
        <div class="field">
          <label class="field-label" for="typhoon-city">比较城市</label>
          <select id="typhoon-city" v-model="cityCode" :disabled="catalogLoading || !cities.length || saving" @change="loadAssessment">
            <option v-for="city in cities" :key="city.code" :value="city.code">{{ city.name }}</option>
          </select>
        </div>
      </div>
      <p class="muted typhoon-hint">换城市会重新计算与同一公报预报点的距离。案例已离线打包，访问出处链接才需要联网。</p>
    </div>

    <div v-if="error" class="alert alert--error" role="alert">
      {{ error }} <button class="btn btn-ghost btn-sm" type="button" @click="cases.length ? loadAssessment() : loadCatalog()">重试</button>
    </div>
    <div v-else-if="catalogLoading || loading" class="card muted" role="status">正在计算台风接近风险…</div>
    <TyphoonEvidence v-else-if="result" :assessment="result.forecast" :verification="result.verification" show-verification />

    <section v-if="canDraft" class="card" aria-label="预警演练草稿">
      <div class="card-head"><h3 class="card-title">创建演练草稿</h3></div>
      <p class="muted">系统将从内置公报重新计算并保存证据。此操作不发布预警，仍需提交并由另一位有权限的用户审核。</p>
      <button v-if="!draftOpen" class="btn btn-primary" type="button" @click="openDraft">填写演练草稿</button>
      <form v-else class="typhoon-draft" @submit.prevent="createDraft">
        <div class="field">
          <label class="field-label" for="typhoon-title">草稿标题</label>
          <input id="typhoon-title" v-model="draft.title" required maxlength="200" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="typhoon-area">研判区域</label>
          <input id="typhoon-area" v-model="draft.area_text" required maxlength="500" :disabled="saving" />
        </div>
        <div class="field">
          <label class="field-label" for="typhoon-impact">影响说明</label>
          <textarea id="typhoon-impact" v-model="draft.impact_text" required maxlength="2000" rows="2" :disabled="saving"></textarea>
        </div>
        <div class="field">
          <label class="field-label" for="typhoon-reason">研判依据</label>
          <textarea id="typhoon-reason" v-model="draft.reasoning_text" required maxlength="20000" rows="2" :disabled="saving"></textarea>
        </div>
        <p v-if="draftError" role="alert" class="alert alert--error">{{ draftError }}</p>
        <button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存台风演练草稿' }}</button>
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
import TyphoonEvidence from '../components/TyphoonEvidence.vue'

const router = useRouter()
const cases = ref([])
const cities = ref([])
const caseId = ref('')
const cityCode = ref('')
const catalogLoading = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const result = ref(null)
const draftOpen = ref(false)
const draftError = ref('')
const draft = reactive({ title: '', area_text: '', impact_text: '', reasoning_text: '' })
let seq = 0
let active = true

const canDraft = computed(() => {
  const forecast = result.value?.forecast
  return auth.hasAnyRole('ANALYST', 'ADMIN') && !loading.value &&
    forecast?.outcome === 'NEAR' && forecast.city.code === cityCode.value && forecast.case.case_id === caseId.value
})

async function loadCatalog() {
  catalogLoading.value = true
  error.value = ''
  try {
    const catalog = await apiFetch('/typhoon/cases')
    if (!active) return
    cases.value = catalog.cases
    cities.value = catalog.cities
    caseId.value = cases.value[0]?.case_id || ''
    cityCode.value = cities.value[0]?.code || ''
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
  draftOpen.value = false
  draftError.value = ''
  error.value = ''
  if (!caseId.value || !cityCode.value) {
    loading.value = false
    error.value = '没有可用的历史案例或城市。'
    return
  }
  loading.value = true
  try {
    const replay = await apiFetch(`/typhoon/cases/${encodeURIComponent(caseId.value)}/assessment?city_code=${encodeURIComponent(cityCode.value)}`)
    if (active && request === seq) result.value = replay
  } catch (e) {
    if (active && request === seq) error.value = e.message
  } finally {
    if (active && request === seq) loading.value = false
  }
}

function openDraft() {
  if (!canDraft.value) return
  const forecast = result.value.forecast
  draft.title = `${forecast.case.name} · ${forecast.city.name}接近风险演练`
  draft.area_text = `${forecast.city.name}代表点（教学取点）`
  draft.impact_text = '仅作教学案例研判，不代表城市实况、灾损或官方预警。'
  draft.reasoning_text = `签发后 24 小时内，最近离散预报点距城市 ${forecast.metric.value} km，达到教学阈值 ≤ ${forecast.metric.threshold} km。`
  draftError.value = ''
  draftOpen.value = true
}

async function createDraft() {
  if (!canDraft.value || saving.value || !draftOpen.value) return
  const body = { case_id: caseId.value, city_code: cityCode.value }
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
    const saved = await apiFetch('/warnings/typhoon', { method: 'POST', body: JSON.stringify(body) })
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
.typhoon-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 340px)); gap: 0 18px; }
.typhoon-hint { margin: 4px 0 0; }
.typhoon-draft { max-width: 730px; }
</style>
