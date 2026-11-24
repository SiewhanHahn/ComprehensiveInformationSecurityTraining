import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './auth'
import { needsAuthRefresh, refreshAuth } from './api'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', component: () => import('./views/Dashboard.vue') },
  { path: '/monitor', component: () => import('./views/Monitor.vue') },
  { path: '/replay', component: () => import('./views/Replay.vue') },
  { path: '/typhoon', component: () => import('./views/Typhoon.vue') },
  { path: '/metrics', component: () => import('./views/Metrics.vue') },
  { path: '/warnings', component: () => import('./views/Warnings.vue') },
  { path: '/warnings/:publicId', component: () => import('./views/WarningDetail.vue') },
  { path: '/review', component: () => import('./views/Review.vue'), meta: { roles: ['REVIEWER', 'ADMIN'] } },
  { path: '/tasks', component: () => import('./views/Tasks.vue'), meta: { roles: ['ANALYST', 'REVIEWER', 'ADMIN'] } },
  { path: '/hazards', component: () => import('./views/Hazards.vue') },
  { path: '/notifications', component: () => import('./views/Notifications.vue') },
  { path: '/audit', component: () => import('./views/Audit.vue'), meta: { role: 'ADMIN' } },
  { path: '/users', component: () => import('./views/Users.vue'), meta: { role: 'ADMIN' } },
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

export function getRouteRedirect(to) {
  if (to.meta.public) return
  if (!auth.user) {
    return to.fullPath && to.fullPath !== '/'
      ? { path: '/login', query: { redirect: to.fullPath } }
      : '/login'
  }
  if (to.meta.roles && !auth.hasAnyRole(...to.meta.roles)) return '/'
  if (to.meta.role && !auth.hasRole(to.meta.role)) return '/'
}

router.beforeEach(async (to) => {
  if (needsAuthRefresh()) {
    try {
      await refreshAuth()
    } catch {
      // The app shell offers a retry without treating a dependency failure as logout.
      return true
    }
  }
  return getRouteRedirect(to) ?? true
})
