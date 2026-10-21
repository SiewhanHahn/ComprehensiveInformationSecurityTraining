const meta = (label, tone) => ({ label, tone })

export const WARNING_STATUS = {
  DRAFT: meta('草稿', 'neutral'),
  PENDING_REVIEW: meta('待审核', 'warning'),
  APPROVED: meta('已批准', 'info'),
  PUBLISHED: meta('已发布', 'success'),
  WITHDRAWN: meta('已撤回', 'neutral'),
  REJECTED: meta('已驳回', 'danger')
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
  WARNING_FEEDBACK: meta('添加反馈', 'purple')
}

export const AUDIT_RESULT = {
  SUCCESS: meta('成功', 'success'),
  DENIED: meta('拒绝', 'danger')
}

export const ROLE_LABELS = {
  ADMIN: '管理员',
  ANALYST: '分析员',
  REVIEWER: '审核员',
  VIEWER: '查看用户'
}

export const RESOURCE_TYPE = {
  auth: meta('认证', 'neutral'),
  warning: meta('预警', 'info')
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
  RAINSTORM: '暴雨'
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
