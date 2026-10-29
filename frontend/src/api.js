import { auth } from './auth'

const ERROR_ZH = {
  INVALID_CREDENTIALS: '用户名或密码错误',
  ACCOUNT_LOCKED: '账号已锁定，请稍后再试',
  ACCOUNT_DISABLED: '账号已停用',
  UNAUTHENTICATED: '未登录或会话已过期',
  FORBIDDEN: '无权限执行此操作',
  SELF_REVIEW_FORBIDDEN: '不能审核自己创建的预警',
  NOT_FOUND: '请求的资源不存在',
  PARTIAL_DATA: '数据不完整，无法创建正式预警',
  INVALID_STATE: '当前状态不允许此操作',
  INVALID_PARAMETER: '请求参数不合法',
  VALIDATION_ERROR: '请求参数不合法（请检查输入）',
  REJECT_REQUIRES_COMMENT: '驳回时必须填写审核意见',
  CSRF: 'CSRF 校验失败，请刷新页面后重试',
  DEPENDENCY_UNAVAILABLE: '依赖服务不可用，请稍后重试',
  USERNAME_EXISTS: '用户名已存在',
  SELF_DISABLE_FORBIDDEN: '不能停用当前登录账号',
  SELF_ADMIN_REMOVAL_FORBIDDEN: '不能撤销当前登录账号的管理员角色',
  LAST_ADMIN_REQUIRED: '系统至少需要一名管理员'
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

function readCookie(name) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return m ? decodeURIComponent(m[1]) : ''
}

export async function apiFetch(path, options = {}) {
  const url = path.startsWith('/api') || path.startsWith('http') ? path : '/api/v1' + path
  const method = (options.method || 'GET').toUpperCase()
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
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
    const csrf = auth.csrf || readCookie('ww_csrf')
    if (csrf && !['GET', 'HEAD'].includes(method)) {
      headers['X-CSRF-Token'] = csrf
    }
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
        detail = ERROR_ZH[code] || detail || data?.detail || `请求失败(${resp.status})`
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
