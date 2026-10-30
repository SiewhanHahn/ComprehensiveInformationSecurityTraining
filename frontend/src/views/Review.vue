<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">审核工作台</h2>
        <span class="page-subtitle">集中处理待审核与待发布预警</span>
      </div>
      <div class="page-actions">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner spinner--dark"></span>
          刷新
        </button>
      </div>
    </div>

    <div class="card">
      <div class="row" role="tablist" aria-label="审核状态筛选" style="gap: 6px; margin-bottom: 16px">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="btn btn-sm"
          :class="activeTab === tab.value ? 'btn-primary' : 'btn-ghost'"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.value"
          @click="switchTab(tab.value)"
        >
          {{ tab.label }}
          <span v-if="activeTab === tab.value && !loading" class="badge badge--sm badge--neutral">{{ rows.length }}</span>
        </button>
      </div>

      <Transition name="slide-fade">
        <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>{{ error }}</div>
        </div>
      </Transition>

      <Transition name="slide-fade">
        <div v-if="notice" class="alert alert--success" role="status" style="margin-bottom: 16px">
          <div>{{ notice }}</div>
        </div>
      </Transition>

      <TableSkeleton v-if="loading" :rows="4" :cols="6" />

      <EmptyState
        v-else-if="!rows.length"
        :title="activeTab === 'PENDING_REVIEW' ? '没有待审核的预警' : '没有待发布的预警'"
        description="新的提交会出现在这里。"
        compact
      />

      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th scope="col">标题</th>
              <th scope="col">城市</th>
              <th scope="col">日期</th>
              <th scope="col">风险等级</th>
              <th scope="col">状态</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in rows" :key="w.public_id">
              <td class="cell-primary">{{ w.title }}</td>
              <td>{{ cityName(w.city_code) }}</td>
              <td class="cell-nowrap">{{ formatDate(w.valid_date) }}</td>
              <td><StatusBadge kind="risk" :value="w.risk_level" size="sm" /></td>
              <td><StatusBadge :value="w.status" size="sm" dot /></td>
              <td>
                <div class="row" style="gap: 6px; flex-wrap: nowrap; align-items: center">
                  <template v-if="activeTab === 'PENDING_REVIEW'">
                    <input
                      v-model="comments[w.public_id]"
                      class="review-comment"
                      placeholder="审核意见（驳回必填）"
                      :aria-label="'审核意见：' + w.title"
                      :disabled="busyId === w.public_id"
                    />
                    <button
                      class="btn btn-primary btn-sm"
                      type="button"
                      :disabled="busyId === w.public_id"
                      @click="review(w, 'APPROVE')"
                    >
                      <span v-if="busyId === w.public_id" class="spinner"></span>
                      批准
                    </button>
                    <button
                      class="btn btn-danger btn-sm"
                      type="button"
                      :disabled="busyId === w.public_id"
                      @click="review(w, 'REJECT')"
                    >
                      驳回
                    </button>
                  </template>
                  <button
                    v-if="activeTab === 'APPROVED'"
                    class="btn btn-primary btn-sm"
                    type="button"
                    :disabled="busyId === w.public_id"
                    @click="publish(w)"
                  >
                    <span v-if="busyId === w.public_id" class="spinner"></span>
                    发布
                  </button>
                  <router-link class="btn btn-ghost btn-sm" :to="'/warnings/' + w.public_id">详情</router-link>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { formatDate } from '../ui/labels'

const tabs = [
  { value: 'PENDING_REVIEW', label: '待审核' },
  { value: 'APPROVED', label: '待发布' }
]

const activeTab = ref('PENDING_REVIEW')
const rows = ref([])
const cities = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyId = ref('')
const comments = ref({})

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await apiFetch(`/warnings?status=${activeTab.value}`)
  } catch (e) {
    error.value = e.message
    rows.value = []
  } finally {
    loading.value = false
  }
}

function switchTab(value) {
  if (activeTab.value === value) return
  activeTab.value = value
  notice.value = ''
  load()
}

async function review(w, decision) {
  const comment = (comments.value[w.public_id] || '').trim()
  if (decision === 'REJECT' && !comment) {
    error.value = '驳回时必须填写审核意见'
    return
  }
  error.value = ''
  notice.value = ''
  busyId.value = w.public_id
  try {
    await apiFetch(`/warnings/${w.public_id}/review`, {
      method: 'POST',
      body: JSON.stringify({ decision, comment })
    })
    notice.value = decision === 'APPROVE' ? `已批准：${w.title}` : `已驳回：${w.title}`
    delete comments.value[w.public_id]
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = ''
  }
}

async function publish(w) {
  error.value = ''
  notice.value = ''
  busyId.value = w.public_id
  try {
    await apiFetch(`/warnings/${w.public_id}/publish`, { method: 'POST' })
    notice.value = `已发布：${w.title}`
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = ''
  }
}

onMounted(async () => {
  const [citiesResult] = await Promise.allSettled([apiFetch('/cities')])
  if (citiesResult.status === 'fulfilled') {
    cities.value = citiesResult.value
  }
  await load()
})
</script>
