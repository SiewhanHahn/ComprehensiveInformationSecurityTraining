<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
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
        <div>
          <div class="login-title">气象灾害预警系统</div>
          <div class="login-sub">多源融合决策支持平台</div>
        </div>
      </div>

      <form @submit.prevent="submit">
        <div class="field">
          <label class="field-label" for="login-username">用户名</label>
          <input
            id="login-username"
            v-model="username"
            autocomplete="username"
            placeholder="请输入用户名"
          />
        </div>
        <div class="field">
          <label class="field-label" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
          />
        </div>

        <Transition name="slide-fade">
          <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
            <span class="alert-icon" aria-hidden="true">!</span>
            <div>{{ error }}</div>
          </div>
        </Transition>

        <button class="btn btn-primary btn-block" type="submit" :disabled="submitting">
          <span v-if="submitting" class="spinner"></span>
          {{ submitting ? '登录中…' : '登录' }}
        </button>
      </form>

      <p class="login-note">演示账号由本地 .env 配置，密码不写死在代码或文档中。</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api'
import { auth } from '../auth'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const res = await apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: username.value, password: password.value })
    })
    auth.set(res.user, res.csrf_token)
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>
