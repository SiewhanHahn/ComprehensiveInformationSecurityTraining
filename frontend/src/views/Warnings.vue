<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">预警管理</h2>
        <span class="page-subtitle">草稿、审核、发布与反馈闭环</span>
      </div>
    </div>

    <div v-if="auth.hasAnyRole('ANALYST', 'ADMIN')" class="card">
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
          <label class="field-label" for="w-impact">影响说明</label>
          <textarea id="w-impact" v-model="form.impact" rows="2"></textarea>
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
          <button class="btn btn-primary" type="submit" :disabled="submitting">
            <span v-if="submitting" class="spinner"></span>
            {{ submitting ? '创建中…' : '创建草稿' }}
          </button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-head">
        <h3 class="card-title">预警列表</h3>
        <span class="card-subtitle">共 {{ warnings.length }} 条</span>
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
                <router-link class="btn btn-ghost btn-sm" :to="'/warnings/' + w.public_id">详情</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api'
import { auth } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { formatDate } from '../ui/labels'

const route = useRoute()
const router = useRouter()

const cities = ref([])
const warnings = ref([])
const loading = ref(true)
const loadError = ref('')
const formError = ref('')
const submitting = ref(false)

const form = reactive({
  city: 'CHANGSHA',
  date: '2024-03-27',
  threshold: 'HEAVY',
  title: '',
  area: '',
  impact: '',
  reason: ''
})

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
}

async function loadWarnings() {
  loading.value = true
  loadError.value = ''
  try {
    warnings.value = await apiFetch('/warnings')
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (route.query.city) form.city = route.query.city
  if (route.query.date) form.date = route.query.date
  if (route.query.threshold) form.threshold = route.query.threshold

  const [citiesResult] = await Promise.allSettled([apiFetch('/cities')])
  if (citiesResult.status === 'fulfilled') {
    cities.value = citiesResult.value
  }
  await loadWarnings()
})

async function create() {
  formError.value = ''
  if (!form.title.trim() || !form.area.trim() || !form.reason.trim()) {
    formError.value = '标题、影响区域、研判依据为必填项'
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
        title: form.title,
        area_text: form.area,
        impact_text: form.impact,
        reasoning_text: form.reason
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
