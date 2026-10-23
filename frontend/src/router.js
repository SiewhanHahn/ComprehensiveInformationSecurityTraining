import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './auth'
import { apiFetch } from './api'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', component: () => import('./views/Dashboard.vue') },
  { path: '/monitor', component: () => import('./views/Monitor.vue') },
  { path: '/replay', component: () => import('./views/Replay.vue') },
  { path: '/metrics', component: () => import('./views/Metrics.vue') },
  { path: '/warnings', component: () => import('./views/Warnings.vue') },
  { path: '/warnings/:publicId', component: () => import('./views/WarningDetail.vue') },
  { path: '/review', component: () => import('./views/Review.vue'), meta: { roles: ['REVIEWER', 'ADMIN'] } },
  { path: '/hazards', component: () => import('./views/Hazards.vue') },
  { path: '/audit', component: () => import('./views/Audit.vue'), meta: { role: 'ADMIN' } },
  { path: '/:pathMatch(.*)*', component: () => import('./views/NotFound.vue'), meta: { public: true } }
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0 }
  }
})

async function refreshAuth() {
  try {
    const res = await apiFetch('/auth/me')
    auth.user = res.user
    auth.ready = true
  } catch (e) {
    auth.clear()
  }
}

router.beforeEach(async (to) => {
  if (!auth.ready) {
    await refreshAuth()
  }
  if (to.meta.public) return true
  if (!auth.user) return '/login'
  if (to.meta.roles && !auth.hasAnyRole(...to.meta.roles)) return '/'
  if (to.meta.role && !auth.hasRole(to.meta.role)) return '/'
  return true
})
