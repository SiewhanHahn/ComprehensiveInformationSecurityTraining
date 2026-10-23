<template>
  <div class="app-shell" :class="{ 'app-shell--guest': !auth.user }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <header v-if="auth.user" class="topbar">
      <div class="topbar-inner">
        <router-link class="brand" to="/" aria-label="返回总览">
          <span class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M7 17.5a4 4 0 0 1-.6-7.95A5.5 5.5 0 0 1 17.2 8.6 4.5 4.5 0 0 1 17 17.5H7Z"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linejoin="round"
              />
              <path d="M12 11.5v4M10.4 14l1.6 1.6 1.6-1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
          <span class="brand-text">
            <span class="brand-title">气象灾害预警系统</span>
            <span class="brand-sub">多源融合决策支持</span>
          </span>
        </router-link>

        <nav id="main-nav" class="nav" :class="{ 'is-open': menuOpen }" aria-label="主导航">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="nav-link"
            :class="{ 'is-active': isActive(item.path) }"
          >
            {{ item.label }}
          </router-link>
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
      <RouterView v-slot="{ Component, route: currentRoute }">
        <Transition name="page" mode="out-in">
          <component :is="Component" :key="currentRoute.path" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from './auth'
import { apiFetch } from './api'
import { roleLabel } from './ui/labels'

const router = useRouter()
const route = useRoute()
const menuOpen = ref(false)

const navItems = computed(() => {
  const items = [
    { path: '/', label: '总览' },
    { path: '/monitor', label: '监测' },
    { path: '/replay', label: '历史回放' },
    { path: '/metrics', label: '指标对比' },
    { path: '/warnings', label: '预警管理' }
  ]
  if (auth.hasAnyRole('REVIEWER', 'ADMIN')) items.push({ path: '/review', label: '审核' })
  items.push({ path: '/hazards', label: '灾种' })
  if (auth.hasRole('ADMIN')) items.push({ path: '/audit', label: '审计' })
  return items
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

watch(
  () => route.path,
  () => {
    menuOpen.value = false
  }
)

async function logout() {
  menuOpen.value = false
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } catch (e) {}
  auth.clear()
  router.push('/login')
}
</script>
