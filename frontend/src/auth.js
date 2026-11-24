import { reactive } from 'vue'

export function readCsrfCookie() {
  const match = globalThis.document?.cookie.match(/(?:^|; *)ww_csrf=([^;]*)/)
  try {
    return match ? decodeURIComponent(match[1]) : ''
  } catch {
    return ''
  }
}

// Account and permissions identify the context in which a view or action was prepared.
export function sessionContext(user) {
  return JSON.stringify([user?.id ?? user?.username ?? null, [...(user?.roles || [])].sort()])
}

export const auth = reactive({
  user: null,
  csrf: '',
  ready: false,
  csrfCookie: '',
  revision: 0,
  refreshError: '',

  set(user, csrf = '', cookie) {
    // A login response's token identifies that response, not a concurrent tab's cookie.
    cookie ??= (this.csrfCookie || readCsrfCookie()) ? csrf : ''
    if (this.csrf !== csrf || this.csrfCookie !== cookie || sessionContext(this.user) !== sessionContext(user)) {
      this.revision += 1
    }
    this.user = user
    this.csrf = csrf
    this.csrfCookie = cookie
    this.refreshError = ''
    this.ready = true
  },

  clear(cookie = readCsrfCookie()) {
    this.set(null, '', cookie)
  },

  hasRole(role) {
    return this.user && this.user.roles && this.user.roles.includes(role)
  },

  hasAnyRole(...roles) {
    return this.user && this.user.roles && roles.some((r) => this.user.roles.includes(r))
  }
})
