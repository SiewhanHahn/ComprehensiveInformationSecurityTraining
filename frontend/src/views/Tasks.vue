<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">任务看板</h2>
        <span class="page-subtitle">预警发布后自动派发处置任务 · 超时由定时扫描升级</span>
      </div>
      <div class="page-actions">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" @click="load()">
          <span v-if="loading" class="spinner spinner--dark"></span>
          刷新
        </button>
      </div>
    </div>

    <div class="row" role="tablist" aria-label="任务状态筛选" style="gap: 6px; margin-bottom: 16px">
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
        <span v-if="activeTab === tab.value && !loading" class="badge badge--sm badge--neutral">
          {{ rows.length }}
        </span>
      </button>
    </div>

    <div class="card">
      <Transition name="slide-fade">
        <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>
            {{ error }}
            <button class="btn btn-ghost btn-sm" type="button" @click="load()">重新加载</button>
          </div>
        </div>
      </Transition>

      <TableSkeleton v-if="loading && !rows.length" :rows="5" :cols="5" />

      <EmptyState
        v-else-if="!rows.length"
        :title="emptyTitle"
        :description="emptyDescription"
      />

      <div v-else class="table-wrap" tabindex="0" role="region" aria-label="任务表格，可横向滚动">
        <table class="table">
          <caption class="sr-only">响应任务列表</caption>
          <thead>
            <tr>
              <th scope="col">预警</th>
              <th scope="col">负责人</th>
              <th scope="col">处置时限</th>
              <th scope="col">状态</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <TransitionGroup name="table-row" tag="tbody">
            <tr v-for="t in rows" :key="t.id">
              <td class="cell-primary cell-wrap">
                <router-link v-if="t.warning_public_id" :to="`/warnings/${t.warning_public_id}`">
                  {{ t.warning_title || shortId(t.warning_public_id) }}
                </router-link>
                <span v-else>{{ t.warning_title }}</span>
              </td>
              <td class="cell-nowrap">{{ t.assignee }}</td>
              <td class="cell-nowrap mono" :title="formatDateTime(t.due_at)">
                {{ formatDateTime(t.due_at) }}
              </td>
              <td class="cell-nowrap">
                <span class="badge-group">
                  <StatusBadge kind="taskStatus" :value="t.status" size="sm" />
                  <span v-if="t.overdue" class="badge badge--danger badge--sm">已逾期</span>
                  <span v-if="t.escalation_level > 0" class="badge badge--orange badge--sm">
                    已升级
                  </span>
                </span>
              </td>
              <td class="cell-wrap">
                <div class="task-actions">
                  <router-link
                    v-if="t.warning_public_id"
                    class="btn btn-ghost btn-sm"
                    :to="`/warnings/${t.warning_public_id}`"
                  >
                    详情
                  </router-link>

                  <template v-if="canAct(t)">
                    <button
                      v-if="t.status === 'PENDING'"
                      class="btn btn-primary btn-sm"
                      type="button"
                      :disabled="busyId === t.id"
                      @click="ack(t)"
                    >
                      接单
                    </button>
                    <template v-else-if="t.status === 'ACKED'">
                      <input
                        v-model="notes[t.id]"
                        class="task-note"
                        placeholder="处置说明"
                        maxlength="1000"
                        :aria-label="`任务 ${t.id} 处置说明`"
                      />
                      <button
                        class="btn btn-primary btn-sm"
                        type="button"
                        :disabled="busyId === t.id"
                        @click="complete(t)"
                      >
                        完成
                      </button>
                    </template>
                  </template>
                </div>
              </td>
            </tr>
          </TransitionGroup>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFetch } from '../api'
import { auth } from '../auth'
import EmptyState from '../components/EmptyState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { formatDateTime, shortId } from '../ui/labels'

const tabs = [
  { value: 'PENDING', label: '待处置' },
  { value: 'ACKED', label: '处置中' },
  { value: 'OVERDUE', label: '已逾期' },
  { value: 'COMPLETED', label: '已完成' }
]

const activeTab = ref('PENDING')
const rows = ref([])
const loading = ref(false)
const error = ref('')
const busyId = ref(null)
const notes = reactive({})

const emptyTitle = computed(() => {
  const label = tabs.find((t) => t.value === activeTab.value)?.label ?? ''
  return `${label}任务为空`
})
const emptyDescription = computed(() => {
  if (activeTab.value === 'OVERDUE') return '没有超过处置时限且尚未完成的任务。'
  if (activeTab.value === 'COMPLETED') return '还没有完成过的任务。'
  return '预警发布后会自动给创建者派发处置任务。'
})

function canAct(task) {
  if (task.status === 'COMPLETED') return false
  return task.assignee === auth.user?.username || auth.hasRole('ADMIN')
}

// 快速切页签时，慢的旧请求不能覆盖新结果；也要按发起时的页签解释数据
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  const tab = activeTab.value
  loading.value = true
  error.value = ''
  try {
    // 「已逾期」不是状态，取全部后按 overdue 过滤
    const query = tab === 'OVERDUE' ? '' : `?status=${tab}`
    const data = await apiFetch(`/response-tasks${query}`)
    if (seq !== loadSeq) return
    rows.value = tab === 'OVERDUE' ? data.filter((t) => t.overdue) : data
  } catch (e) {
    if (seq !== loadSeq) return
    error.value = e.message
    rows.value = []
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function switchTab(value) {
  if (activeTab.value === value) return
  activeTab.value = value
  error.value = ''
  load()
}

async function ack(task) {
  busyId.value = task.id
  error.value = ''
  try {
    await apiFetch(`/response-tasks/${task.id}/ack`, { method: 'POST' })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = null
  }
}

async function complete(task) {
  busyId.value = task.id
  error.value = ''
  try {
    await apiFetch(`/response-tasks/${task.id}/complete`, {
      method: 'POST',
      body: JSON.stringify({ note: notes[task.id] || '' })
    })
    delete notes[task.id]
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.task-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.task-note {
  width: 200px;
}
</style>
