<template>
  <div class="app-shell" :class="{ 'app-shell--guest': !auth.user }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <header v-if="auth.user" class="topbar">
      <div class="topbar-inner">
        <router-link class="brand" to="/" aria-label="返回总览">
          <span class="brand-mark" aria-hidden="true">汛</span>
          <span class="brand-text">
            <span class="brand-title">气象灾害预警系统</span>
            <span class="brand-sub">多源融合决策支持</span>
            <span class="brand-signal" aria-hidden="true">
              <span></span><span></span><span></span><span></span>
            </span>
          </span>
        </router-link>

        <nav id="main-nav" class="nav" :class="{ 'is-open': menuOpen }" aria-label="主导航">
          <div
            v-for="group in navGroups"
            :key="group.label"
            class="nav-item"
            :class="{ 'is-active': isGroupActive(group) }"
          >
            <router-link
              v-if="!group.children"
              :to="group.path"
              class="nav-link"
              :class="{ 'is-active': isGroupActive(group) }"
            >
              {{ group.label }}
            </router-link>
            <template v-else>
              <button
                class="nav-link nav-link--group"
                type="button"
                :aria-expanded="groupOpen === group.label"
                aria-haspopup="true"
                @click="toggleGroup(group.label)"
              >
                {{ group.label }}
              </button>
              <div class="nav-dropdown">
                <router-link
                  v-for="child in group.children"
                  :key="child.path"
                  :to="child.path"
                  class="nav-link"
                  :class="{ 'is-active': isActive(child.path) }"
                >
                  {{ child.label }}
                </router-link>
              </div>
            </template>
          </div>
        </nav>

        <button
          class="nav-toggle"
          type="button"
          aria-label="切换导航菜单"
          aria-controls="main-nav"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>

        <div class="user-area">
          <router-link
            class="topbar-bell"
            to="/notifications"
            :aria-label="unread ? `通知中心，${unread} 条未读` : '通知中心'"
            :aria-current="route.path === '/notifications' ? 'page' : undefined"
          >
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 3a5.5 5.5 0 0 0-5.5 5.5v3.2L5 15h14l-1.5-3.3V8.5A5.5 5.5 0 0 0 12 3Z"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linejoin="round"
              />
              <path
                d="M9.8 18a2.2 2.2 0 0 0 4.4 0"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
            <span v-if="unread" class="topbar-bell-badge">{{ unread > 99 ? '99+' : unread }}</span>
          </router-link>

          <div class="user-chip">
            <span class="avatar" aria-hidden="true">{{ avatarText }}</span>
            <span class="user-meta">
              <span class="user-name">{{ auth.user.display_name || auth.user.username }}</span>
              <span class="role-tag">{{ rolesText }}</span>
            </span>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main id="main-content" class="app-main">
      <div v-if="auth.refreshError && !route.meta.public" class="card">
        <p role="status">{{ auth.refreshError }}</p>
        <button class="btn btn-primary" type="button" :disabled="checkingSession" @click="checkSession">重试</button>
      </div>
      <p v-if="logoutError" role="status">{{ logoutError }}</p>
      <RouterView v-slot="{ Component, route: currentRoute }">
        <Transition name="page" mode="out-in">
          <component
            v-if="canShowPage(currentRoute)"
            :is="Component"
            :key="`${pageContext}:${currentRoute.path}`"
          />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, readCsrfCookie, sessionContext } from './auth'
import { apiFetch, refreshAuth } from './api'
import { getRouteRedirect } from './router'
import { notificationState, refreshUnread, resetUnread } from './notifications'
import { roleLabel } from './ui/labels'

const router = useRouter()
const route = useRoute()
const menuOpen = ref(false)
const groupOpen = ref('')
const unread = computed(() => notificationState.unread)
const pageContext = computed(() => sessionContext(auth.user))
const checkingSession = ref(false)
const logoutError = ref('')

function canShowPage(currentRoute) {
  if (currentRoute.meta.public) return true
  return auth.ready && auth.user && !getRouteRedirect(currentRoute) &&
    (!auth.refreshError || auth.csrfCookie === readCsrfCookie())
}

function syncUnread() {
  if (auth.user) {
    refreshUnread()
  } else {
    resetUnread()
  }
}

async function checkSession() {
  if (document.visibilityState !== 'visible' || checkingSession.value) return
  checkingSession.value = true
  try {
    await refreshAuth()
  } catch {
    // refreshAuth exposes the retry message without changing the known user.
  } finally {
    checkingSession.value = false
  }
}

// 不做定时轮询：/notifications/unread-count 同样走 get_current_user，会刷新会话空闲 TTL，
// 定时轮询等于让人离开后会话永不过期。只挂在用户真实操作（登录、切页、切回标签页）上。
onMounted(() => {
  syncUnread()
  document.addEventListener('visibilitychange', checkSession)
  window.addEventListener('focus', checkSession)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', checkSession)
  window.removeEventListener('focus', checkSession)
})

let loggingOut = false

watch(
  [() => auth.user, () => auth.ready, () => auth.refreshError],
  ([user]) => {
    if (auth.refreshError) return
    syncUnread()
    if (!user && !loggingOut && auth.ready && !route.meta?.public && route.path !== '/login') {
      router.replace(
        route.fullPath && route.fullPath !== '/'
          ? { path: '/login', query: { redirect: route.fullPath } }
          : '/login'
      )
    } else if (user && getRouteRedirect(route) === '/') {
      router.replace('/')
    }
  }
)

const navGroups = computed(() => {
  const groups = [
    { label: '总览', path: '/' },
    {
      label: '数据',
      path: '/monitor',
      children: [
        { path: '/monitor', label: '监测' },
        { path: '/replay', label: '历史回放' },
        { path: '/typhoon', label: '台风路径' },
        { path: '/snow', label: '雪灾回放' },
        { path: '/lightning', label: '雷电回放' },
        { path: '/basic-forecast', label: '基础预测' },
        { path: '/metrics', label: '指标对比' }
      ]
    },
    {
      label: '预警',
      path: '/warnings',
      children: [
        { path: '/warnings', label: '预警管理' },
        ...(auth.hasAnyRole('REVIEWER', 'ADMIN') ? [{ path: '/review', label: '审核' }] : []),
        ...(auth.hasAnyRole('ANALYST', 'REVIEWER', 'ADMIN') ? [{ path: '/tasks', label: '任务看板' }] : []),
        { path: '/hazards', label: '灾种' },
        { path: '/notifications', label: '通知中心' }
      ]
    }
  ]
  if (auth.hasRole('ADMIN')) {
    groups.push({
      label: '管理',
      path: '/audit',
      children: [
        { path: '/audit', label: '审计' },
        { path: '/users', label: '用户管理' }
      ]
    })
  }
  return groups
})

const rolesText = computed(() =>
  (auth.user?.roles || []).map(roleLabel).join(' / ')
)

const avatarText = computed(() => {
  const name = auth.user?.display_name || auth.user?.username || ''
  return name.slice(0, 1).toUpperCase()
})

function isActive(path) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(path + '/')
}

function isGroupActive(group) {
  if (!group.children) return isActive(group.path)
  return group.children.some((c) => isActive(c.path))
}

function toggleGroup(label) {
  groupOpen.value = groupOpen.value === label ? '' : label
}

watch(
  () => route.path,
  () => {
    menuOpen.value = false
    groupOpen.value = ''
    // 页面切换时顺手刷新未读数（/notifications 不在 60 秒 GET 缓存白名单内）
    syncUnread()
  }
)

async function logout() {
  menuOpen.value = false
  logoutError.value = ''
  loggingOut = true
  try {
    try {
      await apiFetch('/auth/logout', { method: 'POST' })
    } catch (error) {
      if (auth.user) {
        logoutError.value = error.message || '退出失败，请重试'
        return
      }
    }
    auth.clear('')
    await router.push('/login')
  } finally {
    loggingOut = false
  }
}
</script>
