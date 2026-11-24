<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">预警管理</h2>
        <span class="page-subtitle">草稿、审核、发布与反馈闭环</span>
      </div>
    </div>

    <div v-if="showPreview" class="card">
      <div class="card-head">
        <h3 class="card-title">回放依据</h3>
        <span class="card-subtitle">{{ preview?.city?.name || cityName(form.city) }} · {{ form.date }}</span>
        <span v-if="preview" style="margin-left: auto">
          <StatusBadge kind="dataStatus" :value="preview.data_status" />
        </span>
      </div>
      <div v-if="previewLoading" class="skeleton skeleton-line" style="height: 80px"></div>
      <div v-else-if="previewError" class="alert alert--error" role="alert">
        <span class="alert-icon" aria-hidden="true">!</span>
        <div>
          {{ previewError }}
          <button class="btn btn-ghost btn-sm" type="button" @click="loadPreview">重新加载</button>
        </div>
      </div>
      <template v-else-if="preview">
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-value">{{ preview.fused_mm == null ? '—' : preview.fused_mm }}</div>
            <div class="summary-label">等权融合（mm）</div>
          </div>
          <div class="summary-item">
            <div class="summary-value"><StatusBadge kind="risk" :value="preview.risk_level" /></div>
            <div class="summary-label">教学风险等级</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">{{ preview.models.length }}</div>
            <div class="summary-label">参与模式</div>
          </div>
        </div>
        <div class="row" style="gap: 6px">
          <span
            v-for="m in preview.models"
            :key="m.model"
            class="badge badge--sm"
            :class="m.precipitation_mm == null ? 'badge--danger' : 'badge--neutral'"
          >
            {{ modelLabel(m.model) }} {{ m.precipitation_mm == null ? '缺测' : m.precipitation_mm }}
          </span>
        </div>
        <p v-if="preview.data_status !== 'COMPLETE'" class="muted" style="margin: 10px 0 0">
          数据不完整，不能创建正式预警；请更换日期或城市。
        </p>
        <p v-else-if="!preview.risk_level" class="muted" style="margin: 10px 0 0">
          融合值未达到所选阈值，不能创建正式预警。
        </p>
      </template>
      <p v-else class="muted">请选择城市、日期和阈值以核对回放数据。</p>
    </div>

    <div v-if="canDraft" class="card">
      <div class="card-head">
        <h3 class="card-title">新建预警草稿</h3>
        <span class="card-subtitle">基于完整回放数据创建，提交后进入审核</span>
      </div>
      <form @submit.prevent="create">
        <div class="form-grid">
          <div class="field">
            <label class="field-label" for="w-city">城市</label>
            <select id="w-city" v-model="form.city">
              <option v-for="c in cities" :key="c.code" :value="c.code">{{ c.name }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="w-date">日期</label>
            <input id="w-date" v-model="form.date" type="date" />
          </div>
          <div class="field">
            <label class="field-label" for="w-threshold">阈值</label>
            <select id="w-threshold" v-model="form.threshold">
              <option value="MODERATE">10mm</option>
              <option value="HEAVY">25mm</option>
              <option value="STORM">50mm</option>
            </select>
          </div>
        </div>

        <div class="field" style="margin-top: 16px">
          <label class="field-label" for="w-title">标题</label>
          <input id="w-title" v-model="form.title" placeholder="例如：长沙市 3 月 27 日大雨预警" />
        </div>
        <div class="field" style="margin-top: 16px">
          <label class="field-label" for="w-area">影响区域</label>
          <input id="w-area" v-model="form.area" placeholder="例如：长沙市主城区" />
        </div>
        <div class="field" style="margin-top: 16px">
          <label class="field-label" for="w-impact">影响说明（必填）</label>
          <textarea id="w-impact" v-model="form.impact" rows="2" maxlength="2000" required></textarea>
        </div>
        <div class="field" style="margin-top: 16px">
          <label class="field-label" for="w-reason">研判依据</label>
          <textarea id="w-reason" v-model="form.reason" rows="3" placeholder="说明四模式融合值与判定依据"></textarea>
        </div>

        <Transition name="slide-fade">
          <div v-if="formError" class="alert alert--error" role="alert" style="margin-top: 16px">
            <span class="alert-icon" aria-hidden="true">!</span>
            <div>{{ formError }}</div>
          </div>
        </Transition>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="submitting || !canCreate">
            <span v-if="submitting" class="spinner"></span>
            {{ submitting ? '创建中…' : '创建草稿' }}
          </button>
          <span v-if="!canCreate" class="muted">当前回放数据不完整，无法创建</span>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-head">
        <h3 class="card-title">预警列表</h3>
        <span class="card-subtitle">共 {{ warnings.length }} 条</span>
      </div>

      <div class="row" role="tablist" aria-label="预警状态筛选" style="gap: 6px; margin-bottom: 16px">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="btn btn-sm"
          :class="activeStatus === tab.value ? 'btn-primary' : 'btn-ghost'"
          type="button"
          role="tab"
          :aria-selected="activeStatus === tab.value"
          @click="switchStatus(tab.value)"
        >
          {{ tab.label }}
        </button>
      </div>

      <Transition name="slide-fade">
        <div v-if="loadError" class="alert alert--error" role="alert" style="margin-bottom: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>
            {{ loadError }}
            <button class="btn btn-ghost btn-sm" type="button" @click="loadWarnings">重新加载</button>
          </div>
        </div>
      </Transition>

      <TableSkeleton v-if="loading" :rows="4" :cols="6" />

      <EmptyState
        v-else-if="!warnings.length"
        title="暂无预警记录"
        description="创建第一条草稿后，会在这里看到状态流转。"
        compact
      />

      <div v-else class="table-wrap">
        <table class="table">
          <caption class="sr-only">预警列表</caption>
          <thead>
            <tr>
              <th scope="col">标题</th>
              <th scope="col">城市</th>
              <th scope="col">日期</th>
              <th scope="col">等级</th>
              <th scope="col">状态</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in warnings" :key="w.public_id">
              <td class="cell-primary">{{ w.title }}</td>
              <td>{{ cityName(w.city_code) }}</td>
              <td class="cell-nowrap">{{ formatDate(w.valid_date) }}</td>
              <td><StatusBadge kind="risk" :value="w.risk_level" size="sm" /></td>
              <td><StatusBadge :value="w.status" size="sm" dot /></td>
              <td>
                <span v-if="w.status === 'CANCELLED'" class="muted">—</span>
                <router-link v-else class="btn btn-ghost btn-sm" :to="'/warnings/' + w.public_id">详情</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api'
import { auth } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { WARNING_STATUS, formatDate, modelLabel } from '../ui/labels'

const route = useRoute()
const router = useRouter()

const cities = ref([])
const warnings = ref([])
const loading = ref(true)
const loadError = ref('')
const formError = ref('')
const submitting = ref(false)
const activeStatus = ref('')
const preview = ref(null)
const previewLoading = ref(false)
const previewError = ref('')
const requestedPreviewKey = ref('')
let listSeq = 0
let previewSeq = 0

const isViewerOnly = computed(
  () => auth.hasRole('VIEWER') && !auth.hasAnyRole('ADMIN', 'ANALYST', 'REVIEWER')
)

const tabs = computed(() => {
  if (isViewerOnly.value) return [{ value: 'PUBLISHED', label: '已发布' }]
  return [
    { value: '', label: '全部' },
    { value: 'DRAFT', label: '草稿' },
    { value: 'PENDING_REVIEW', label: '待审核' },
    { value: 'APPROVED', label: '已批准' },
    { value: 'PUBLISHED', label: '已发布' },
    { value: 'WITHDRAWN', label: '已撤回' },
    { value: 'REJECTED', label: '已驳回' },
    { value: 'CANCELLED', label: WARNING_STATUS.CANCELLED.label }
  ]
})

const canDraft = computed(() => auth.hasAnyRole('ANALYST', 'ADMIN'))
const showPreview = computed(() =>
  canDraft.value || Boolean(route.query.city && route.query.date && route.query.threshold)
)

const form = reactive({
  city: 'CHANGSHA',
  date: '2024-03-27',
  threshold: 'HEAVY',
  title: '',
  area: '',
  impact: '',
  reason: ''
})

const previewKey = computed(() => {
  const { city, date, threshold } = form
  if (!showPreview.value || !city || !date || !threshold) return ''
  return new URLSearchParams({ city_code: city, date, threshold_code: threshold }).toString()
})

const canCreate = computed(() =>
  canDraft.value && previewKey.value !== '' && previewKey.value === requestedPreviewKey.value &&
  !previewLoading.value && preview.value?.data_status === 'COMPLETE' && Boolean(preview.value.risk_level)
)

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
}

async function loadWarnings() {
  const seq = ++listSeq
  loading.value = true
  loadError.value = ''
  try {
    const query = activeStatus.value ? `/warnings?status=${activeStatus.value}` : '/warnings'
    const data = await apiFetch(query)
    if (seq === listSeq) warnings.value = data
  } catch (e) {
    if (seq !== listSeq) return
    loadError.value = e.message
    warnings.value = []
  } finally {
    if (seq === listSeq) loading.value = false
  }
}

function switchStatus(value) {
  if (activeStatus.value === value) return
  activeStatus.value = value
  loadWarnings()
}

async function loadPreview() {
  const key = previewKey.value
  if (key === requestedPreviewKey.value && (previewLoading.value || preview.value)) return
  const seq = ++previewSeq
  requestedPreviewKey.value = key
  preview.value = null
  previewError.value = ''
  previewLoading.value = Boolean(key)
  if (!key) return
  try {
    const data = await apiFetch(`/replay?${key}`)
    if (seq === previewSeq) preview.value = data
  } catch (e) {
    if (seq === previewSeq) previewError.value = e.message
  } finally {
    if (seq === previewSeq) previewLoading.value = false
  }
}

watch(previewKey, loadPreview)

onMounted(async () => {
  if (route.query.city) form.city = route.query.city
  if (route.query.date) form.date = route.query.date
  if (route.query.threshold) form.threshold = route.query.threshold
  activeStatus.value = isViewerOnly.value ? 'PUBLISHED' : ''

  const previewTask = loadPreview()
  const [citiesResult] = await Promise.allSettled([apiFetch('/cities')])
  if (citiesResult.status === 'fulfilled') {
    cities.value = citiesResult.value
  }
  await Promise.all([previewTask, loadWarnings()])
})

async function create() {
  if (submitting.value || !canDraft.value) return
  formError.value = ''
  if (!canCreate.value) {
    formError.value = '请先确认当前选择的回放数据完整且融合值达到阈值'
    return
  }
  const title = form.title.trim()
  const area = form.area.trim()
  const impact = form.impact.trim()
  const reason = form.reason.trim()
  if (!title || !area || !impact || !reason) {
    formError.value = '标题、影响区域、影响说明、研判依据为必填项'
    return
  }
  submitting.value = true
  try {
    const w = await apiFetch('/warnings', {
      method: 'POST',
      body: JSON.stringify({
        city_code: form.city,
        valid_date: form.date,
        threshold_code: form.threshold,
        title,
        area_text: area,
        impact_text: impact,
        reasoning_text: reason
      })
    })
    router.push('/warnings/' + w.public_id)
  } catch (e) {
    formError.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>
