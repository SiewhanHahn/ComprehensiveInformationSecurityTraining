import { reactive } from 'vue'

export const auth = reactive({
  user: null,
  csrf: '',
  ready: false,

  set(user, csrf) {
    this.user = user
    this.csrf = csrf || this.csrf
    this.ready = true
  },

  clear() {
    this.user = null
    this.csrf = ''
    this.ready = true
  },

  hasRole(role) {
    return this.user && this.user.roles && this.user.roles.includes(role)
  },

  hasAnyRole(...roles) {
    return this.user && this.user.roles && roles.some((r) => this.user.roles.includes(r))
  }
})
