<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">审计日志</h2>
        <span class="page-subtitle">登录与预警操作留痕 · 时间按北京时间显示</span>
      </div>
      <div class="page-actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="loading"
          @click="load(page)"
        >
          <span v-if="loading" class="spinner spinner--dark"></span>
          刷新
        </button>
      </div>
    </div>

    <div class="card">
      <Transition name="slide-fade">
        <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>
            {{ error }}
            <button class="btn btn-ghost btn-sm" type="button" @click="load(page)">重新加载</button>
          </div>
        </div>
      </Transition>

      <TableSkeleton v-if="loading && !rows.length" :rows="6" :cols="7" />

      <EmptyState
        v-else-if="!rows.length"
        :title="page > 1 ? '本页暂无记录' : '暂无审计记录'"
        :description="page > 1 ? '可能已经翻到末尾。' : '登录或执行预警操作后会自动留痕。'"
      >
        <button v-if="page > 1" class="btn btn-ghost btn-sm" type="button" @click="goToPage(page - 1)">
          返回上一页
        </button>
      </EmptyState>

      <template v-else>
        <div
          ref="tableRegion"
          class="table-wrap"
          tabindex="0"
          role="region"
          aria-label="审计日志表格，可横向滚动"
        >
          <table class="table table--audit">
            <caption class="sr-only">审计日志列表</caption>
            <thead>
              <tr>
                <th scope="col">时间（北京时间）</th>
                <th scope="col">操作</th>
                <th scope="col">资源</th>
                <th scope="col">结果</th>
                <th scope="col">角色</th>
                <th scope="col">原因</th>
                <th scope="col">IP</th>
              </tr>
            </thead>
            <TransitionGroup name="table-row" tag="tbody">
              <tr v-for="r in rows" :key="r.id">
                <td class="cell-nowrap mono" :title="r.created_at">
                  {{ formatDateTime(r.created_at) }}
                </td>
                <td><StatusBadge kind="auditAction" :value="r.action" size="sm" /></td>
                <td>
                  <div class="resource-cell">
                    <span class="badge badge--sm" :class="`badge--${resourceTone(r.resource_type)}`">
                      {{ resourceLabel(r.resource_type) }}
                    </span>
                    <router-link
                      v-if="r.resource_type === 'warning' && r.resource_id"
                      class="id-link"
                      :to="`/warnings/${r.resource_id}`"
                      :title="r.resource_id"
                    >
                      {{ shortId(r.resource_id) }}
                    </router-link>
                    <span
                      v-else-if="r.resource_id"
                      class="id-link mono"
                      :title="r.resource_id"
                    >
                      {{ shortId(r.resource_id) }}
                    </span>
                  </div>
                </td>
                <td><StatusBadge kind="auditResult" :value="r.result" size="sm" /></td>
                <td>
                  <span v-if="!splitRoles(r.actor_role).length" class="badge badge--neutral badge--sm">
                    未认证
                  </span>
                  <span v-else class="badge-group">
                    <span
                      v-for="role in splitRoles(r.actor_role)"
                      :key="role"
                      class="badge badge--neutral badge--sm"
                      :title="role"
                    >
                      {{ roleLabel(role) }}
                    </span>
                  </span>
                </td>
                <td class="cell-wrap" :title="r.reason || ''">{{ reasonLabel(r.reason) }}</td>
                <td class="cell-nowrap mono">{{ dash(r.ip_address) }}</td>
              </tr>
            </TransitionGroup>
          </table>
        </div>

        <PaginationBar
          :page="page"
          :page-size="pageSize"
          :has-next="hasNext"
          :loading="loading"
          @change="goToPage"
        />
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import {
  RESOURCE_TYPE,
  REASON_LABELS,
  dash,
  formatDateTime,
  roleLabel,
  shortId,
  splitRoles
} from '../ui/labels'

const PAGE_SIZE = 20

const rows = ref([])
const page = ref(1)
const pageSize = PAGE_SIZE
const hasNext = ref(false)
const loading = ref(false)
const error = ref('')
const tableRegion = ref(null)

const reduceMotion = computed(
  () =>
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
)

function resourceLabel(value) {
  return RESOURCE_TYPE[value]?.label || value || '—'
}

function resourceTone(value) {
  return RESOURCE_TYPE[value]?.tone || 'neutral'
}

function reasonLabel(value) {
  if (value === null || value === undefined || value === '') return '—'
  return REASON_LABELS[value] || value
}

async function load(target) {
  const targetPage = Math.max(1, target || 1)
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch(`/audit-logs?page=${targetPage}&page_size=${PAGE_SIZE}`)
    rows.value = Array.isArray(data) ? data : []
    page.value = targetPage
    hasNext.value = rows.value.length === PAGE_SIZE
  } catch (e) {
    error.value = e.message
    rows.value = []
    hasNext.value = false
  } finally {
    loading.value = false
  }
}

async function goToPage(target) {
  const next = Number(target)
  if (!Number.isInteger(next) || next < 1) return
  if (next > page.value && !hasNext.value) return
  await load(next)
  if (tableRegion.value) {
    tableRegion.value.scrollIntoView({
      behavior: reduceMotion.value ? 'auto' : 'smooth',
      block: 'start'
    })
  }
}

onMounted(() => load(1))
</script>
