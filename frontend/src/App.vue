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
const groupOpen = ref('')

const navGroups = computed(() => {
  const groups = [
    { label: '总览', path: '/' },
    {
      label: '数据',
      path: '/monitor',
      children: [
        { path: '/monitor', label: '监测' },
        { path: '/replay', label: '历史回放' },
        { path: '/metrics', label: '指标对比' }
      ]
    },
    {
      label: '预警',
      path: '/warnings',
      children: [
        { path: '/warnings', label: '预警管理' },
        { path: '/review', label: '审核' },
        { path: '/hazards', label: '灾种' }
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
