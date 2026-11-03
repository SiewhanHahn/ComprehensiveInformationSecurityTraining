<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">通知中心</h2>
        <span class="page-subtitle">
          订阅灾种与城市，预警发布或撤回时在站内提醒 · 未读 {{ unread }} 条
        </span>
      </div>
      <div class="page-actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="busy || !unread"
          @click="readAll"
        >
          全部标记已读
        </button>
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" @click="refresh">
          <span v-if="loading" class="spinner spinner--dark"></span>
          刷新
        </button>
      </div>
    </div>

    <Transition name="slide-fade">
      <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
        <span class="alert-icon" aria-hidden="true">!</span>
        <div>
          {{ error }}
          <button class="btn btn-ghost btn-sm" type="button" @click="refresh">重新加载</button>
        </div>
      </div>
    </Transition>

    <div class="grid grid-2 grid--notify">
      <div class="card">
        <div class="card-head">
          <div>
            <h3 class="card-title">我的通知</h3>
            <p class="card-subtitle">按时间倒序 · 时间按北京时间显示</p>
          </div>
          <div class="segmented" role="group" aria-label="通知筛选">
            <button
              type="button"
              class="segmented-item"
              :class="{ 'is-active': !unreadOnly }"
              :aria-pressed="!unreadOnly"
              @click="setFilter(false)"
            >
              全部
            </button>
            <button
              type="button"
              class="segmented-item"
              :class="{ 'is-active': unreadOnly }"
              :aria-pressed="unreadOnly"
              @click="setFilter(true)"
            >
              未读
            </button>
          </div>
        </div>

        <TableSkeleton v-if="loading && !items.length" :rows="5" :cols="2" />

        <EmptyState
          v-else-if="!items.length"
          :title="unreadOnly ? '没有未读通知' : '还没有通知'"
          :description="
            unreadOnly
              ? '切换「全部」查看历史通知。'
              : '在右侧订阅灾种或城市，预警发布后会自动收到站内通知。'
          "
        />

        <template v-else>
          <ul class="notif-list">
            <li
              v-for="n in items"
              :key="n.id"
              class="notif-item"
              :class="{ 'is-unread': !n.read_at }"
            >
              <div class="notif-top">
                <StatusBadge kind="notificationKind" :value="n.kind" size="sm" />
                <span v-if="!n.read_at" class="notif-dot" aria-label="未读"></span>
                <time class="notif-time mono" :datetime="n.created_at">
                  {{ formatDateTime(n.created_at) }}
                </time>
              </div>
              <p class="notif-title">{{ n.title }}</p>
              <p class="notif-body">{{ n.body }}</p>
              <div class="notif-actions">
                <router-link
                  v-if="canOpenWarning(n)"
                  class="btn btn-ghost btn-sm"
                  :to="`/warnings/${n.resource_id}`"
                >
                  查看预警
                </router-link>
                <button
                  v-if="!n.read_at"
                  class="btn btn-ghost btn-sm"
                  type="button"
                  :disabled="busy"
                  @click="markRead(n)"
                >
                  标记已读
                </button>
              </div>
            </li>
          </ul>

          <PaginationBar
            :page="page"
            :page-size="PAGE_SIZE"
            :has-next="hasNext"
            :loading="loading"
            @change="goToPage"
          />
        </template>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h3 class="card-title">订阅设置</h3>
            <p class="card-subtitle">灾种与城市都选「全部」表示不限</p>
          </div>
        </div>

        <form @submit.prevent="addSubscription">
          <div class="form-grid">
            <div class="field">
              <label class="field-label" for="sub-hazard">灾种</label>
              <select id="sub-hazard" v-model="form.hazard">
                <option value="*">全部灾种</option>
                <option v-for="(label, code) in HAZARD_TYPE" :key="code" :value="code">
                  {{ label }}
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label" for="sub-city">城市</label>
              <select id="sub-city" v-model="form.city">
                <option value="">全部城市</option>
                <option v-for="c in cities" :key="c.code" :value="c.code">{{ c.name }}</option>
              </select>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" type="submit" :disabled="busy">添加订阅</button>
          </div>
        </form>

        <p class="field-hint" style="margin-top: 12px">
          当前仅暴雨已接入数据，其余灾种暂无预警产生。
        </p>

        <EmptyState
          v-if="!subs.length"
          compact
          title="还没有订阅"
          description="订阅后，匹配的预警发布时会自动出现在通知中心。"
        />

        <ul v-else class="sub-tags">
          <li v-for="s in subs" :key="s.id" class="sub-tag">
            <span class="badge badge--info badge--sm">{{ hazardLabel(s.hazard_type) }}</span>
            <span class="badge badge--neutral badge--sm">{{ cityLabel(s.city_code) }}</span>
            <button
              class="sub-remove"
              type="button"
              :aria-label="`取消订阅 ${hazardLabel(s.hazard_type)} ${cityLabel(s.city_code)}`"
              :disabled="busy"
              @click="removeSubscription(s)"
            >
              ×
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFetch } from '../api'
import { auth } from '../auth'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { notificationState, refreshUnread } from '../notifications'
import { HAZARD_TYPE, formatDateTime } from '../ui/labels'

const PAGE_SIZE = 20

const items = ref([])
const total = ref(0)
const page = ref(1)
const unread = computed(() => notificationState.unread)
const unreadOnly = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')

const cities = ref([])
const subs = ref([])

const form = reactive({ hazard: '*', city: '' })

const hasNext = computed(() => page.value * PAGE_SIZE < total.value)

function hazardLabel(code) {
  return code === '*' ? '全部灾种' : HAZARD_TYPE[code] || code
}

// 已撤回的预警对「仅查看者」不可见（get_visible_warning 一律 404），不要给出必然打不开的链接
function canOpenWarning(n) {
  if (n.resource_type !== 'warning') return false
  if (n.kind === 'WARNING_PUBLISHED') return true
  return auth.hasAnyRole('ADMIN', 'ANALYST', 'REVIEWER')
}

function cityLabel(code) {
  if (!code) return '全部城市'
  return cities.value.find((c) => c.code === code)?.name || code
}

// 快速切筛选/翻页时，慢的旧请求不能覆盖新结果
let loadSeq = 0

async function loadNotifications(target = 1) {
  const targetPage = Math.max(1, target || 1)
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({
      page: String(targetPage),
      page_size: String(PAGE_SIZE),
      unread_only: String(unreadOnly.value)
    })
    const data = await apiFetch(`/notifications?${query}`)
    if (seq !== loadSeq) return
    items.value = data.items || []
    total.value = data.total || 0
    page.value = data.page || targetPage
  } catch (e) {
    if (seq !== loadSeq) return
    error.value = e.message
    items.value = []
    total.value = 0
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadSubscriptions() {
  try {
    subs.value = await apiFetch('/subscriptions')
  } catch (e) {
    // 不要静默降级成空数组：否则后端出错时页面看起来像「还没订阅过」
    error.value = e.message
    subs.value = []
  }
}

async function loadCities() {
  try {
    cities.value = await apiFetch('/cities')
  } catch (e) {
    error.value = e.message
    cities.value = []
  }
}

async function refresh() {
  await Promise.all([loadNotifications(page.value), loadSubscriptions()])
}

function setFilter(value) {
  if (unreadOnly.value === value) return
  unreadOnly.value = value
  loadNotifications(1)
}

async function goToPage(target) {
  const next = Number(target)
  if (!Number.isInteger(next) || next < 1) return
  if (next > page.value && !hasNext.value) return
  await loadNotifications(next)
}

async function markRead(notification) {
  busy.value = true
  try {
    await apiFetch(`/notifications/${notification.id}/read`, { method: 'POST' })
    notification.read_at = new Date().toISOString()
    await refreshUnread()
    if (unreadOnly.value) {
      // 未读筛选下这一行要消失：重新取当前页，而不是本地删行——
      // 本地删行会让 total 和后端偏移错开，下一页会漏掉最新的那条
      await loadNotifications(page.value)
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function readAll() {
  busy.value = true
  try {
    await apiFetch('/notifications/read-all', { method: 'POST' })
    await Promise.all([loadNotifications(page.value), refreshUnread()])
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function addSubscription() {
  busy.value = true
  error.value = ''
  try {
    await apiFetch('/subscriptions', {
      method: 'POST',
      body: JSON.stringify({ hazard_type: form.hazard, city_code: form.city })
    })
    form.city = ''
    await loadSubscriptions()
    // 新订阅可能匹配到近期已发布的预警，扫描补投需要时间；提示用户刷新即可
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function removeSubscription(subscription) {
  busy.value = true
  try {
    await apiFetch(`/subscriptions/${subscription.id}`, { method: 'DELETE' })
    await loadSubscriptions()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadCities(), loadSubscriptions(), loadNotifications(1)])
})
</script>

<style scoped>
.grid--notify {
  align-items: start;
}

.notif-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.notif-item {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-soft);
}

.notif-item.is-unread {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px rgba(53, 201, 230, 0.12);
}

.notif-top {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.notif-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 8px var(--color-primary);
}

.notif-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-faint);
}

.notif-title {
  margin: var(--space-2) 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.notif-body {
  margin: var(--space-1) 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.notif-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.sub-tags {
  list-style: none;
  margin: var(--space-4) 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.sub-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 4px 6px 4px 4px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface-soft);
}

.sub-remove {
  border: none;
  background: transparent;
  color: var(--color-text-faint);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}

.sub-remove:hover:not(:disabled) {
  color: var(--danger);
}

.segmented {
  display: inline-flex;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.segmented-item {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 6px 12px;
  cursor: pointer;
}

.segmented-item.is-active {
  background: var(--color-surface-soft);
  color: var(--color-primary);
}
</style>
