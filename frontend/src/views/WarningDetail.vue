<template>
  <div class="page">
    <router-link class="back-link" to="/warnings">← 返回预警列表</router-link>

    <div v-if="loading" class="card">
      <div class="skeleton skeleton-line" style="width: 40%; height: 22px"></div>
      <div class="skeleton skeleton-line" style="width: 65%"></div>
      <div class="skeleton skeleton-line" style="height: 180px; margin-top: 16px"></div>
    </div>

    <div v-else-if="!w" class="card">
      <EmptyState title="无法加载预警" :description="error || '记录不存在或无权访问。'">
        <router-link class="btn btn-primary btn-sm" to="/warnings">返回列表</router-link>
      </EmptyState>
    </div>

    <template v-else>
      <div class="card">
        <div class="card-head">
          <h3 class="card-title">闭环进度</h3>
          <span class="card-subtitle">监测 → 预测 → 研判 → 预警 → 发布 → 响应 → 反馈</span>
        </div>
        <ClosedLoopStepper :stages="stages" />
      </div>

      <div class="card">
        <div class="card-head" style="align-items: center">
          <h2 class="page-title" style="font-size: 24px">{{ w.title }}</h2>
          <StatusBadge :value="w.status" dot />
        </div>

        <div class="row muted" style="margin-bottom: 16px; gap: 12px">
          <span class="mono" :title="w.public_id">编号 {{ shortId(w.public_id, 10, 6) }}</span>
          <span>·</span>
          <span>{{ hazardLabel(w.hazard_type) }}</span>
          <span>·</span>
          <span>创建人 {{ w.created_by }}</span>
        </div>

        <div class="detail-grid">
          <div class="detail-item">
            <div class="detail-label">城市</div>
            <div class="detail-value">{{ w.city_name || cityName(w.city_code) }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">有效日期</div>
            <div class="detail-value">{{ formatDate(w.valid_date) }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">{{ w.metric?.label || '融合累计' }}</div>
            <div class="detail-value">{{ w.metric ? `${w.metric.value} ${w.metric.unit}` : `${w.fused_mm} mm` }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">风险等级</div>
            <div class="detail-value"><StatusBadge kind="risk" :value="w.risk_level" /></div>
          </div>

          <div class="detail-block">
            <div class="detail-label">影响区域</div>
            <div class="detail-value">{{ w.area_text }}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">影响说明</div>
            <div class="detail-value">{{ w.impact_text || '—' }}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">研判依据</div>
            <div class="detail-value">{{ w.reasoning_text }}</div>
          </div>
        </div>

        <WarningVersionHistory
          v-if="auth.hasAnyRole('REVIEWER', 'ADMIN') && w.version_no >= 1"
          :key="w.public_id"
          :warning="w"
        />

        <p v-if="w.status === 'REJECTED' && w.rejection_comment" role="note"><strong>驳回意见：</strong>{{ w.rejection_comment }}</p>
        <form v-if="canManageDraft && editForm" style="margin-top: 16px" @submit.prevent="saveEdit">
          <h3 class="card-title">编辑草稿</h3>
          <div v-for="field in draftFields" :key="field.name" class="field" style="margin-top: 12px">
            <label class="field-label" :for="'edit-' + field.name">{{ field.label }}</label>
            <textarea
              v-if="field.rows"
              :id="'edit-' + field.name"
              v-model="editForm[field.name]"
              :rows="field.rows"
              :maxlength="field.maxLength"
              :required="field.required"
              :disabled="busy"
            ></textarea>
            <input
              v-else
              :id="'edit-' + field.name"
              v-model="editForm[field.name]"
              :maxlength="field.maxLength"
              :required="field.required"
              :disabled="busy"
            />
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit" :disabled="busy">保存修改</button>
            <button class="btn btn-ghost" type="button" :disabled="busy" @click="discardEdit">放弃修改</button>
          </div>
        </form>

        <Transition name="slide-fade">
          <div v-if="error" class="alert alert--error" role="alert" style="margin-top: 16px">
            <span class="alert-icon" aria-hidden="true">!</span>
            <div>{{ error }}</div>
          </div>
        </Transition>

        <Transition name="slide-fade">
          <div v-if="notice" class="alert alert--success" role="status" style="margin-top: 16px">
            <div>{{ notice }}</div>
          </div>
        </Transition>

        <div class="action-bar">
          <template v-if="canManageDraft && !editForm">
            <button class="btn btn-primary" type="button" :disabled="busy" @click="act('submit')">
              {{ w.status === 'REJECTED' ? '重新提交审核' : '提交审核' }}
            </button>
            <button class="btn btn-ghost" type="button" :disabled="busy" @click="startEdit">编辑草稿</button>
            <button class="btn btn-danger" type="button" :disabled="busy" @click="act('cancel')">取消草稿</button>
          </template>

          <template v-if="!isMine && auth.hasAnyRole('REVIEWER', 'ADMIN') && w.status === 'PENDING_REVIEW'">
            <div class="review-panel">
              <input v-model="comment" placeholder="审核意见" aria-label="审核意见" />
            </div>
            <button class="btn btn-primary" type="button" :disabled="busy" @click="act('review', 'APPROVE')">
              批准
            </button>
            <button class="btn btn-danger" type="button" :disabled="busy" @click="act('review', 'REJECT')">
              驳回
            </button>
          </template>

          <input v-if="auth.hasAnyRole('REVIEWER', 'ADMIN') && ['APPROVED', 'PUBLISHED'].includes(w.status)"
            v-model="actionReason" maxlength="500" placeholder="发布或撤回原因（可选）" aria-label="发布或撤回原因" />
          <button
            v-if="auth.hasAnyRole('REVIEWER', 'ADMIN') && w.status === 'APPROVED'"
            class="btn btn-primary"
            type="button"
            :disabled="busy"
            @click="act('publish')"
          >
            发布
          </button>
          <button
            v-if="auth.hasAnyRole('REVIEWER', 'ADMIN') && w.status === 'PUBLISHED'"
            class="btn btn-danger"
            type="button"
            :disabled="busy"
            @click="act('withdraw')"
          >
            撤回
          </button>
        </div>

        <div
          v-if="(auth.hasRole('ANALYST') || auth.hasRole('ADMIN')) && (w.status === 'PUBLISHED' || w.status === 'WITHDRAWN')"
          style="margin-top: 20px"
        >
          <h4 style="margin-bottom: 8px">添加反馈</h4>
          <div class="form-row">
            <div class="field" style="min-width: 160px">
              <label class="field-label" for="f-status">反馈状态</label>
              <select id="f-status" v-model="feedbackStatus">
                <option value="RECEIVED">已接收</option>
                <option value="PROCESSING">处置中</option>
                <option value="COMPLETED">已完成</option>
              </select>
            </div>
            <div class="field" style="flex: 1; min-width: 240px">
              <label class="field-label" for="f-content">反馈内容</label>
              <textarea id="f-content" v-model="feedbackContent" rows="2" placeholder="响应与反馈内容"></textarea>
            </div>
            <div class="field">
              <button class="btn btn-primary" type="button" :disabled="busy" @click="act('feedback')">
                提交反馈
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="canUseTasks && w.status !== 'CANCELLED'" class="card">
        <div class="card-head">
          <h3 class="card-title">响应任务</h3>
          <span class="card-subtitle">发布时自动派发给预警创建者（创建者已停用时改派发布人）· 时限按配置计算</span>
        </div>

        <div v-if="taskError" class="alert alert--error" role="alert" style="margin-bottom: 16px">
          <span class="alert-icon" aria-hidden="true">!</span>
          <div>响应任务加载失败：{{ taskError }}</div>
        </div>

        <EmptyState
          v-if="!currentTask && !taskError"
          compact
          title="尚未派发任务"
          description="预警批准发布后会自动生成一条处置任务。"
        />

        <template v-else-if="currentTask">
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">负责人</span>
              <span class="detail-value">{{ currentTask.assignee }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">状态</span>
              <span class="detail-value">
                <StatusBadge kind="taskStatus" :value="currentTask.status" size="sm" />
                <span v-if="currentTask.overdue" class="badge badge--danger badge--sm">已逾期</span>
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">处置时限</span>
              <span class="detail-value mono">{{ formatDateTime(currentTask.due_at) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">升级</span>
              <span class="detail-value">
                {{ currentTask.escalation_level ? `已升级 ${currentTask.escalation_level} 次` : '未升级' }}
              </span>
            </div>
          </div>

          <div v-if="currentTask.note" class="detail-block">
            <span class="detail-label">处置说明</span>
            <p class="detail-value">{{ currentTask.note }}</p>
          </div>

          <div v-if="canActOnTask" class="action-bar">
            <button
              v-if="currentTask.status === 'PENDING'"
              class="btn btn-primary"
              type="button"
              :disabled="taskBusy !== null"
              @click="actOnTask('ack')"
            >
              接单
            </button>
            <template v-else-if="currentTask.status === 'ACKED'">
              <div class="review-panel">
                <input
                  v-model="taskNote"
                  class="review-comment"
                  placeholder="处置说明（可选）"
                  maxlength="1000"
                />
              </div>
              <button
                class="btn btn-primary"
                type="button"
                :disabled="taskBusy !== null"
                @click="actOnTask('complete')"
              >
                完成任务
              </button>
            </template>
          </div>
        </template>
      </div>

      <TyphoonEvidence v-if="w.typhoon_assessment" :assessment="w.typhoon_assessment" />
      <SnowEvidence v-else-if="w.snow_assessment" :assessment="w.snow_assessment" />
      <LightningEvidence v-else-if="w.lightning_assessment" :assessment="w.lightning_assessment" />
      <div v-else-if="w.hazard_type === 'RAINSTORM'" class="card">
        <div class="card-head">
          <h3 class="card-title">融合追溯</h3>
          <span class="card-subtitle">
            {{ w.dataset_version ? '数据集 ' + w.dataset_version : '未记录数据集版本' }}
          </span>
        </div>

        <div v-if="w.models && w.models.length" class="table-wrap">
          <table class="table">
            <thead>
              <tr><th scope="col">模式</th><th scope="col">24h 累计降水 (mm)</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in w.models" :key="m.model">
                <td class="cell-primary">{{ m.model }}</td>
                <td>{{ m.precipitation_mm == null ? '缺测' : m.precipitation_mm }}</td>
              </tr>
              <tr>
                <td class="cell-primary">等权融合</td>
                <td class="cell-accent">{{ w.fused_mm }}</td>
              </tr>
              <tr>
                <td class="cell-primary">ECMWF 基线</td>
                <td>{{ w.baseline_mm ?? '—' }}</td>
              </tr>
              <tr>
                <td class="cell-primary">ERA5 代理标签</td>
                <td>
                  {{ w.proxy_label_mm ?? '—' }}
                  <span class="muted">（再分析，非站点实测）</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState
          v-else
          title="无融合输入明细"
          description="该预警创建时未记录四模式输入（早期数据）。"
          compact
        />

        <ChartPanel
          v-if="w.models && w.models.length"
          title="四模式输入"
          subtitle="柱高为 24h 累计降水；虚线为基线与代理标签"
          :option="modelBarOption"
          :height="250"
          aria-label="四模式降水与基线、代理标签对比柱状图"
        />

        <p class="muted" style="margin-top: 12px">
          融合值为四模式 24h 累计降水等权平均；ERA5 代理标签仅用于评估，不参与预警判定。
        </p>
      </div>

      <div class="card">
        <div class="card-head">
          <h3 class="card-title">反馈记录</h3>
          <span class="card-subtitle">共 {{ feedbacks.length }} 条</span>
        </div>

        <EmptyState v-if="!feedbacks.length" title="暂无反馈" description="预警发布后可追加处置反馈。" compact />

        <TransitionGroup v-else name="table-row" tag="div" class="feedback-list">
          <div v-for="f in feedbacks" :key="f.created_at + f.content" class="feedback-item">
            <div class="feedback-meta">
              <StatusBadge kind="feedback" :value="f.response_status" size="sm" />
              <span>{{ f.created_by }}</span>
              <span>·</span>
              <span>{{ formatDateTime(f.created_at) }}</span>
            </div>
            <div class="feedback-content">{{ f.content }}</div>
          </div>
        </TransitionGroup>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '../api'
import { auth } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import ClosedLoopStepper from '../components/ClosedLoopStepper.vue'
import ChartPanel from '../components/ChartPanel.vue'
import TyphoonEvidence from '../components/TyphoonEvidence.vue'
import SnowEvidence from '../components/SnowEvidence.vue'
import LightningEvidence from '../components/LightningEvidence.vue'
import WarningVersionHistory from '../components/WarningVersionHistory.vue'
import { modelBar } from '../charts/options'
import { HAZARD_TYPE, formatDate, formatDateTime, shortId } from '../ui/labels'

const route = useRoute()

const w = ref(null)
const cities = ref([])
const feedbacks = ref([])
const error = ref('')
const notice = ref('')
const loading = ref(true)
const busy = ref(false)
const editForm = ref(null)
const draftFields = [
  { name: 'title', label: '标题', maxLength: 200, required: true },
  { name: 'area_text', label: '影响区域', maxLength: 500, required: true },
  { name: 'impact_text', label: '影响说明', maxLength: 2000, rows: 2, required: true },
  { name: 'reasoning_text', label: '研判依据', maxLength: 20000, rows: 3, required: true }
]
const comment = ref('')
const actionReason = ref('')
const feedbackStatus = ref('RECEIVED')
const feedbackContent = ref('')

const tasks = ref([])
const taskError = ref('')
const taskNote = ref('')
const taskBusy = ref(null)

const canUseTasks = computed(() => auth.hasAnyRole('ANALYST', 'REVIEWER', 'ADMIN'))
const currentTask = computed(() => tasks.value[0] || null)
const canActOnTask = computed(() => {
  const task = currentTask.value
  if (!task || task.status === 'COMPLETED') return false
  return auth.hasRole('ADMIN') || task.assignee === auth.user?.username
})

const isMine = computed(
  () => w.value && auth.user && w.value.created_by === auth.user.username
)

const canManageDraft = computed(() =>
  isMine.value && auth.hasAnyRole('ANALYST', 'ADMIN') &&
  (w.value.status === 'DRAFT' || w.value.status === 'REJECTED')
)

const modelBarOption = computed(() => {
  const item = w.value
  if (!item?.models?.length) return null
  return modelBar(item.models, {
    baseline: item.baseline_mm,
    proxy: item.proxy_label_mm
  })
})

const stages = computed(() => {
  const item = w.value
  if (!item) return []
  const s = item.status
  const fb = [...feedbacks.value].sort((a, b) =>
    String(a.created_at).localeCompare(String(b.created_at))
  )
  const latest = fb[fb.length - 1]
  const hasFeedback = fb.length > 0
  const completed = fb.some((f) => f.response_status === 'COMPLETED')

  const warningState = s === 'CANCELLED'
    ? 'cancelled'
    : s === 'DRAFT' || s === 'REJECTED' ? 'current' : 'done'
  const publishState =
    s === 'PUBLISHED' || s === 'WITHDRAWN'
      ? 'done'
      : s === 'PENDING_REVIEW' || s === 'APPROVED'
        ? 'current'
        : 'pending'
  // 响应阶段优先由响应任务驱动；没有任务时退回原来的「有没有反馈」判断
  const task = currentTask.value
  const responseState = task
    ? task.status === 'COMPLETED'
      ? 'done'
      : 'current'
    : hasFeedback
      ? 'done'
      : s === 'PUBLISHED'
        ? 'current'
        : 'pending'
  const feedbackState = completed ? 'done' : hasFeedback ? 'current' : 'pending'

  let publishTime = ''
  let publishNote = ''
  if (s === 'PENDING_REVIEW') {
    publishNote = '待审核'
  } else if (s === 'APPROVED') {
    publishTime = formatDateTime(item.approved_at)
    publishNote = '已批准，待发布'
  } else if (s === 'PUBLISHED') {
    publishTime = formatDateTime(item.published_at)
    publishNote = '已发布'
  } else if (s === 'WITHDRAWN') {
    publishTime = formatDateTime(item.withdrawn_at)
    publishNote = '已撤回'
  }

  const forecastNotes = { TYPHOON: '历史航运公报', SNOW_DISASTER: '历史单批次降雪预报',
    THUNDERSTORM: '历史 HRRR 雷电预报' }
  return [
    { key: 'monitor', label: '监测', state: 'done', note: '离线数据快照' },
    { key: 'forecast', label: '预测', state: 'done', note: forecastNotes[item.hazard_type] || '四模式 24h' },
    { key: 'analysis', label: '研判', state: 'done', note: item.metric ? `${item.metric.value} ${item.metric.unit}` : `${item.fused_mm} mm` },
    {
      key: 'warning',
      label: '预警',
      state: warningState,
      time: s !== 'CANCELLED' && item.submitted_at ? formatDateTime(item.submitted_at) : '',
      role: '分析员',
      note: s === 'CANCELLED' ? '已取消，未发布' : ''
    },
    {
      key: 'publish',
      label: '发布',
      state: publishState,
      time: publishTime,
      role: '审核员',
      note: publishNote
    },
    {
      key: 'response',
      label: '响应',
      state: responseState,
      time: task?.completed_at
        ? formatDateTime(task.completed_at)
        : latest
          ? formatDateTime(latest.created_at)
          : '',
      role: task ? `负责人 ${task.assignee}` : '分析员/管理员',
      note: task
        ? task.status === 'COMPLETED'
          ? s === 'WITHDRAWN' && !task.acked_at
            ? '已随撤回关闭'
            : '已完成处置'
          : task.overdue
            ? '已逾期'
            : `时限 ${formatDateTime(task.due_at)}`
        : ''
    },
    {
      key: 'feedback',
      label: '反馈',
      state: feedbackState,
      time: latest ? formatDateTime(latest.created_at) : '',
      role: '分析员/管理员'
    }
  ]
})

function cityName(code) {
  return cities.value.find((c) => c.code === code)?.name || code || '—'
}

function hazardLabel(value) {
  return HAZARD_TYPE[value] || value || '—'
}

async function load(showSkeleton = true) {
  if (showSkeleton) loading.value = true
  error.value = ''
  taskError.value = ''
  const id = route.params.publicId
  try {
    const [detail, list] = await Promise.all([
      apiFetch(`/warnings/${id}`),
      apiFetch(`/warnings/${id}/feedback`)
    ])
    w.value = detail
    feedbacks.value = list
  } catch (e) {
    // 动作成功后的刷新失败不置空，保留现有数据并提示
    if (showSkeleton) w.value = null
    error.value = e.message
    loading.value = false
    return
  }

  // 响应任务是辅助信息：它失败只影响任务卡，不能把已经取到的预警主体一起清掉
  try {
    tasks.value = canUseTasks.value ? await apiFetch(`/response-tasks?warning=${id}`) : []
  } catch (e) {
    tasks.value = []
    taskError.value = e.message
  } finally {
    loading.value = false
  }
}

async function actOnTask(kind) {
  const task = currentTask.value
  if (!task) return
  taskBusy.value = task.id
  error.value = ''
  notice.value = ''
  try {
    if (kind === 'ack') {
      await apiFetch(`/response-tasks/${task.id}/ack`, { method: 'POST' })
      notice.value = '已接单，请按期完成处置'
    } else {
      await apiFetch(`/response-tasks/${task.id}/complete`, {
        method: 'POST',
        body: JSON.stringify({ note: taskNote.value })
      })
      taskNote.value = ''
      notice.value = '响应任务已完成'
    }
    await load(false)
  } catch (e) {
    error.value = e.message
  } finally {
    taskBusy.value = null
  }
}

onMounted(async () => {
  const [citiesResult] = await Promise.allSettled([apiFetch('/cities')])
  if (citiesResult.status === 'fulfilled') {
    cities.value = citiesResult.value
  }
  await load()
})

function startEdit() {
  if (!canManageDraft.value || busy.value || editForm.value) return
  error.value = ''
  notice.value = ''
  editForm.value = Object.fromEntries(draftFields.map(({ name }) => [name, w.value[name] ?? '']))
}

function discardEdit() {
  if (busy.value) return
  editForm.value = null
  error.value = ''
}

async function saveEdit() {
  if (!canManageDraft.value || busy.value || !editForm.value) return
  error.value = ''
  notice.value = ''
  const changes = {}
  for (const { name, label, required } of draftFields) {
    const value = editForm.value[name].trim()
    if (required && !value) {
      error.value = `${label}为必填项`
      return
    }
    if (value !== (w.value[name] ?? '').trim()) changes[name] = value || null
  }
  // PATCH 只传实际变动的字段，不重写旧记录的其他内容。
  if (Object.keys(changes).length === 0) {
    discardEdit()
    return
  }
  busy.value = true
  try {
    const updated = await apiFetch(`/warnings/${w.value.public_id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes)
    })
    w.value = { ...w.value, ...updated }
    editForm.value = null
    notice.value = '草稿修改已保存'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function act(kind, decision) {
  if (busy.value || !w.value) return
  if (kind === 'submit' || kind === 'cancel') {
    if (!canManageDraft.value || editForm.value) return
    if (kind === 'submit' && !w.value.impact_text?.trim()) {
      error.value = '请先编辑草稿，补全影响说明后再提交'
      return
    }
    if (kind === 'cancel' && !window.confirm('确定取消这条草稿？取消后不能再编辑或提交审核。')) return
  }
  error.value = ''
  notice.value = ''
  busy.value = true
  const id = w.value.public_id
  try {
    if (kind === 'submit' || kind === 'cancel') {
      const updated = await apiFetch(`/warnings/${id}/${kind}`, { method: 'POST' })
      w.value = { ...w.value, ...updated }
      notice.value = kind === 'cancel' ? '草稿已取消' : '已提交审核'
      // 更新已由动作响应确认；取消后的详情与反馈接口会返回 404。
      return
    } else if (kind === 'review') {
      if (decision === 'REJECT' && !comment.value.trim()) {
        error.value = '驳回时必须填写审核意见'
        return
      }
      await apiFetch(`/warnings/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({ decision, comment: comment.value, review_token: w.value.review_token })
      })
      notice.value = decision === 'APPROVE' ? '已批准' : '已驳回'
    } else if (kind === 'publish' || kind === 'withdraw') {
      const reason = actionReason.value.trim()
      await apiFetch(`/warnings/${id}/${kind}`, { method: 'POST', ...(reason && { body: JSON.stringify({ reason }) }) })
      actionReason.value = ''
      notice.value = kind === 'publish' ? '已发布' : '已撤回'
    } else if (kind === 'feedback') {
      if (!feedbackContent.value.trim()) {
        error.value = '反馈内容不能为空'
        return
      }
      await apiFetch(`/warnings/${id}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          response_status: feedbackStatus.value,
          content: feedbackContent.value
        })
      })
      feedbackContent.value = ''
      notice.value = '反馈已提交'
    }
    await load(false)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>
