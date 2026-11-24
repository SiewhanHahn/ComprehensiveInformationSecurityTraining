import { auth, readCsrfCookie, sessionContext } from './auth'

const ERROR_ZH = {
  INVALID_CREDENTIALS: '用户名或密码错误',
  ACCOUNT_DISABLED: '账号已停用',
  UNAUTHENTICATED: '未登录或会话已过期',
  FORBIDDEN: '无权限执行此操作',
  SELF_REVIEW_FORBIDDEN: '不能审核自己创建的预警',
  NOT_FOUND: '请求的资源不存在',
  PARTIAL_DATA: '数据不完整，无法创建正式预警',
  THRESHOLD_NOT_REACHED: '融合值未达到所选阈值，无法创建预警',
  INVALID_STATE: '当前状态不允许此操作',
  INVALID_PARAMETER: '请求参数不合法',
  VALIDATION_ERROR: '请求参数不合法（请检查输入）',
  REJECT_REQUIRES_COMMENT: '驳回时必须填写审核意见',
  CSRF: 'CSRF 校验失败，请刷新页面后重试',
  DEPENDENCY_UNAVAILABLE: '依赖服务不可用，请稍后重试',
  INTERNAL_ERROR: '服务器内部错误，请稍后重试',
  USERNAME_EXISTS: '用户名已存在',
  SELF_DISABLE_FORBIDDEN: '不能停用当前登录账号',
  SELF_ADMIN_REMOVAL_FORBIDDEN: '不能撤销当前登录账号的管理员角色',
  LAST_ADMIN_REQUIRED: '系统至少需要一名管理员',
  SUBSCRIPTION_EXISTS: '该订阅已存在',
  LOGIN_RATE_LIMITED: '尝试过于频繁，请稍后再试',
  METHOD_NOT_ALLOWED: '请求方法不被允许',
  HTTP_ERROR: '请求失败'
}

// 仅缓存静态参考数据，避免页面切换时重复请求后端；认证/预警/审计不缓存。
const GET_CACHE_TTL_MS = 60_000
const CACHEABLE_PATHS = ['/cities', '/metrics/experiments']
const getCache = new Map()
const inFlight = new Map()

function isCacheable(url) {
  const path = url.split('?')[0]
  if (!path.startsWith('/api/v1')) return false
  const rest = path.slice('/api/v1'.length)
  return CACHEABLE_PATHS.some((p) => rest === p || rest.startsWith(p + '/'))
}

let pendingRefresh

export function needsAuthRefresh() {
  return !auth.ready || Boolean(auth.refreshError) || auth.csrfCookie !== readCsrfCookie()
}

export function refreshAuth() {
  const cookie = readCsrfCookie()
  const revision = auth.revision
  if (pendingRefresh?.cookie === cookie && pendingRefresh.revision === revision) {
    return pendingRefresh.promise
  }

  const job = { cookie, revision }
  const isCurrent = () => revision === auth.revision && cookie === readCsrfCookie()
  const refreshIfNeeded = () => needsAuthRefresh() ? refreshAuth() : undefined
  async function load() {
    let user
    try {
      user = (await apiFetch('/auth/me'))?.user
      if (!user) throw new Error('Missing user in auth response')
    } catch (error) {
      if (!isCurrent()) return refreshIfNeeded()
      if (error.status === 401 && error.code === 'UNAUTHENTICATED') {
        auth.clear(cookie)
        return
      }
      auth.refreshError = error.status === 503 ? error.message : '暂时无法确认登录状态，请稍后重试'
      throw error
    }
    if (!isCurrent()) return refreshIfNeeded()
    // Only keep an in-memory fallback when there was no readable cookie and the account is unchanged.
    const csrf = cookie || (!auth.csrfCookie && auth.user?.id === user.id ? auth.csrf : '')
    auth.set(user, csrf, cookie)
  }
  job.promise = load().finally(() => {
    if (pendingRefresh === job) pendingRefresh = undefined
  })
  pendingRefresh = job
  return job.promise
}

export async function apiFetch(path, options = {}) {
  const url = path.startsWith('/api') || path.startsWith('http') ? path : '/api/v1' + path
  const method = (options.method || 'GET').toUpperCase()
  const endpoint = url.split('?')[0]
  const isLogin = endpoint.endsWith('/auth/login')
  const isAuthMe = endpoint.endsWith('/auth/me')
  const isWrite = !['GET', 'HEAD', 'OPTIONS'].includes(method) && !isLogin
  const cacheable = method === 'GET' && isCacheable(url)

  if (cacheable) {
    const cached = getCache.get(url)
    if (cached && cached.expires > Date.now()) {
      return cached.data
    }
    if (inFlight.has(url)) {
      return inFlight.get(url)
    }
  }

  const request = (async () => {
    let cookie = readCsrfCookie()
    if (isWrite && auth.ready && needsAuthRefresh()) {
      const previousContext = sessionContext(auth.user)
      await refreshAuth()
      cookie = readCsrfCookie()
      // Don't submit an action prepared under a different account or set of permissions.
      if (previousContext !== sessionContext(auth.user) || cookie !== auth.csrfCookie) {
        const error = new Error('登录身份或权限已变化，请确认当前页面后重试')
        error.code = 'SESSION_CHANGED'
        throw error
      }
    }
    const revision = auth.revision
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
    const csrf = cookie || auth.csrf
    if (isWrite && csrf) headers['X-CSRF-Token'] = csrf
    const resp = await fetch(url, {
      credentials: 'include',
      ...options,
      headers
    })
    if (resp.status === 204) return null
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      // 后端统一返回 { error: { code, message, request_id } }；detail 分支仅兼容未经全局处理的旧格式
      let code = data?.error?.code
      let detail = data?.error?.message
      if (Array.isArray(data?.detail)) {
        code = ''
        detail = '请求参数不合法（请检查输入）'
      } else {
        code = code || data?.detail
        // 后端 message 为准，ERROR_ZH 仅在没有后端文案时兜底
        detail = detail || ERROR_ZH[code] || data?.detail || `请求失败(${resp.status})`
      }
      // Only the current session's confirmed auth failure should sign this tab out.
      if (resp.status === 401 && code === 'UNAUTHENTICATED' && !isLogin && !isAuthMe &&
          revision === auth.revision && cookie === readCsrfCookie()) {
        auth.clear(cookie)
      }
      const err = new Error(detail)
      err.status = resp.status
      err.code = code
      throw err
    }
    if (cacheable && data !== null) {
      getCache.set(url, { data, expires: Date.now() + GET_CACHE_TTL_MS })
    }
    return data
  })()

  if (cacheable) {
    inFlight.set(url, request)
    request.then(
      () => inFlight.delete(url),
      () => inFlight.delete(url)
    )
  }

  return request
}
