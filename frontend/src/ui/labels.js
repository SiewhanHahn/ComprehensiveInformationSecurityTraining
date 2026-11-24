const meta = (label, tone) => ({ label, tone })

export const WARNING_STATUS = {
  DRAFT: meta('草稿', 'neutral'),
  PENDING_REVIEW: meta('待审核', 'warning'),
  APPROVED: meta('已批准', 'info'),
  PUBLISHED: meta('已发布', 'success'),
  WITHDRAWN: meta('已撤回', 'neutral'),
  REJECTED: meta('已驳回', 'danger'),
  CANCELLED: meta('已取消', 'neutral')
}

export const RISK_LEVEL = {
  BLUE: meta('蓝色（低）', 'blue'),
  YELLOW: meta('黄色（中）', 'yellow'),
  ORANGE: meta('橙色（高）', 'orange')
}

export const FEEDBACK_STATUS = {
  RECEIVED: meta('已接收', 'info'),
  PROCESSING: meta('处置中', 'warning'),
  COMPLETED: meta('已完成', 'success')
}

export const TASK_STATUS = {
  PENDING: meta('待处置', 'warning'),
  ACKED: meta('处置中', 'info'),
  COMPLETED: meta('已完成', 'success')
}

export const AUDIT_ACTION = {
  LOGIN_SUCCESS: meta('登录成功', 'success'),
  LOGIN_FAILED: meta('登录失败', 'danger'),
  LOGOUT: meta('退出登录', 'neutral'),
  WARNING_CREATE: meta('创建预警', 'info'),
  WARNING_UPDATE: meta('更新预警', 'info'),
  WARNING_SUBMIT: meta('提交审核', 'warning'),
  WARNING_REVIEW: meta('审核预警', 'purple'),
  WARNING_PUBLISH: meta('发布预警', 'success'),
  WARNING_WITHDRAW: meta('撤回预警', 'orange'),
  WARNING_CANCEL: meta('取消预警', 'neutral'),
  WARNING_FEEDBACK: meta('添加反馈', 'purple'),
  SUBSCRIPTION_CREATE: meta('新增订阅', 'info'),
  SUBSCRIPTION_DELETE: meta('取消订阅', 'neutral'),
  NOTIFICATION_BACKFILL: meta('通知补投', 'purple'),
  RESPONSE_TASK_CREATE: meta('派发任务', 'info'),
  RESPONSE_TASK_ACK: meta('接单', 'info'),
  RESPONSE_TASK_COMPLETE: meta('完成任务', 'success'),
  RESPONSE_TASK_CLOSE: meta('撤回关闭任务', 'warning'),
  RESPONSE_TASK_ESCALATE: meta('超时升级', 'danger'),
  USER_CREATE: meta('创建用户', 'info'),
  USER_STATUS_CHANGE: meta('启用/停用用户', 'warning'),
  USER_ROLES_CHANGE: meta('修改用户角色', 'warning'),
  USER_PASSWORD_RESET: meta('重置密码', 'purple'),
  USER_MANAGE_DENIED: meta('用户管理被拒', 'danger'),
  PERMISSION_DENIED: meta('权限拒绝', 'danger')
}

export const AUDIT_RESULT = {
  SUCCESS: meta('成功', 'success'),
  DENIED: meta('拒绝', 'danger')
}

export const ROLE_LABELS = {
  ADMIN: '管理员',
  ANALYST: '分析员',
  REVIEWER: '审核员',
  VIEWER: '查看用户',
  SYSTEM: '系统定时任务'
}

export const RESOURCE_TYPE = {
  auth: meta('认证', 'neutral'),
  warning: meta('预警', 'info'),
  subscription: meta('订阅', 'purple'),
  notification: meta('通知', 'blue'),
  response_task: meta('响应任务', 'orange'),
  USER: meta('用户', 'blue')
}

export const NOTIFICATION_KIND = {
  WARNING_PUBLISHED: meta('预警发布', 'danger'),
  WARNING_WITHDRAWN: meta('预警撤回', 'neutral'),
  TASK_ASSIGNED: meta('任务指派', 'info'),
  TASK_OVERDUE: meta('任务超时', 'warning'),
  TASK_ESCALATED: meta('超时升级', 'danger')
}

export const REASON_LABELS = {
  'unknown user': '未知用户',
  locked: '账号已锁定',
  disabled: '账号已停用',
  'bad password': '密码错误',
  APPROVE: '审核通过',
  REJECT: '审核驳回'
}

export const DATA_STATUS = {
  COMPLETE: meta('数据完整', 'success'),
  PARTIAL: meta('数据不完整', 'warning')
}

export const HAZARD_TYPE = {
  RAINSTORM: '暴雨',
  TYPHOON: '台风',
  HEATWAVE: '高温',
  DROUGHT: '干旱',
  THUNDERSTORM: '雷电',
  FOG: '大雾',
  FLASH_FLOOD: '山洪',
  URBAN_WATERLOGGING: '城市内涝'
}

export const MODEL_LABELS = {
  ecmwf_ifs025: 'ECMWF',
  gfs_global: 'GFS',
  icon_global: 'ICON',
  gem_global: 'GEM'
}

export const DATASET_TYPE = {
  FORECAST: '预报数据',
  ERA5_LABEL: 'ERA5 代理标签',
  OBSERVATION: '站点观测'
}

export const SOURCE_TYPE = {
  FORECAST: '数值预报',
  REANALYSIS: '再分析',
  OBSERVATION: '站点观测'
}

export function modelLabel(code) {
  return MODEL_LABELS[code] || code
}

export function datasetTypeLabel(code) {
  return DATASET_TYPE[code] || code || '—'
}

export function sourceTypeLabel(code) {
  return SOURCE_TYPE[code] || code || '—'
}

export function getMeta(map, value) {
  if (value === null || value === undefined || value === '') return null
  return map[value] || { label: String(value), tone: 'neutral' }
}

export function dash(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

export function splitRoles(value) {
  if (!value) return []
  return [...new Set(String(value).split(',').map((r) => r.trim()).filter(Boolean))]
}

export function roleLabel(role) {
  return ROLE_LABELS[role] || role
}

export function shortId(value, head = 8, tail = 4) {
  if (value === null || value === undefined || value === '') return '—'
  const id = String(value)
  if (id.length <= 14) return id
  return `${id.slice(0, head)}…${id.slice(-tail)}`
}

const DATE_TIME_FORMAT = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  hourCycle: 'h23'
})

function parseUtc(value) {
  if (value === null || value === undefined || value === '') return null
  let text = String(value)
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(text) && !/(Z|[+-]\d{2}:?\d{2})$/.test(text)) {
    text = text.replace(' ', 'T') + 'Z'
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

export function utcDateTimeAttribute(value) {
  return parseUtc(value)?.toISOString() ?? undefined
}

export function formatDateTime(value) {
  const date = parseUtc(value)
  if (!date) return dash(value)
  const parts = DATE_TIME_FORMAT.formatToParts(date)
  const pick = (type) => parts.find((p) => p.type === type)?.value || ''
  return `${pick('year')}-${pick('month')}-${pick('day')} ${pick('hour')}:${pick('minute')}:${pick('second')}`
}

export function formatDate(value) {
  if (!value) return '—'
  const text = String(value)
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text
  const date = parseUtc(text)
  if (!date) return text
  const parts = DATE_TIME_FORMAT.formatToParts(date)
  const pick = (type) => parts.find((p) => p.type === type)?.value || ''
  return `${pick('year')}-${pick('month')}-${pick('day')}`
}
