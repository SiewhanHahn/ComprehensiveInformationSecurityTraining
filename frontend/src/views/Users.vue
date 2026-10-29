<template>
  <div class="page">
    <div class="page-head">
      <div class="page-heading">
        <h2 class="page-title">用户管理</h2>
        <span class="page-subtitle">管理员账号、角色与访问状态管理</span>
      </div>
      <div class="page-actions">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading || !!busy" @click="load(page)">
          <span v-if="loading" class="spinner spinner--dark"></span>刷新
        </button>
      </div>
    </div>

    <Transition name="slide-fade">
      <div v-if="error" class="alert alert--error" role="alert" style="margin-bottom: 16px">
        <span class="alert-icon" aria-hidden="true">!</span><div>{{ error }}</div>
      </div>
    </Transition>
    <Transition name="slide-fade">
      <div v-if="notice" class="alert alert--success" role="status" style="margin-bottom: 16px">
        {{ notice }}
      </div>
    </Transition>

    <div class="users-layout">
      <section class="card">
        <div class="card-head"><h3 class="card-title">创建账号</h3></div>
        <form @submit.prevent="createUser">
          <div class="field"><label class="field-label" for="new-username">用户名</label><input id="new-username" v-model="createForm.username" autocomplete="off" placeholder="3–64 位字母、数字、_.-" /></div>
          <div class="field"><label class="field-label" for="new-display">显示名称</label><input id="new-display" v-model="createForm.display_name" autocomplete="off" placeholder="1–100 个字符" /></div>
          <div class="field"><label class="field-label" for="new-password">初始密码</label><input id="new-password" v-model="createForm.password" type="password" autocomplete="new-password" placeholder="8–128 位，不会回显" /></div>
          <div class="field">
            <span class="field-label">角色（至少选择一项）</span>
            <div class="role-checks"><label v-for="role in roles" :key="role" class="check-label"><input v-model="createForm.roles" type="checkbox" :value="role" />{{ roleName(role) }}</label></div>
          </div>
          <div v-if="createError" class="form-error" role="alert">{{ createError }}</div>
          <div class="form-actions"><button class="btn btn-primary" type="submit" :disabled="!!busy"><span v-if="busy === 'create'" class="spinner"></span>创建账号</button></div>
        </form>
      </section>

      <section class="card">
        <div class="card-head"><h3 class="card-title">账号列表</h3><span class="muted">共 {{ total }} 个账号</span></div>
        <TableSkeleton v-if="loading && !users.length" :rows="6" :cols="5" />
        <EmptyState v-else-if="!users.length" title="暂无用户" description="请使用左侧表单创建第一个账号。" />
        <template v-else>
          <div class="table-wrap" tabindex="0" role="region" aria-label="用户列表，可横向滚动">
            <table class="table users-table"><caption class="sr-only">用户列表</caption><thead><tr><th>用户名</th><th>显示名称</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
              <tbody><tr v-for="user in users" :key="user.id" :class="{ 'row-selected': selected?.id === user.id }">
                <td class="cell-primary mono">{{ user.username }}</td><td>{{ user.display_name }}</td>
                <td><span class="badge-group"><span v-for="role in user.roles" :key="role" class="badge badge--neutral badge--sm">{{ roleName(role) }}</span></span></td>
                <td><span class="badge badge--sm" :class="user.is_active ? 'badge--success' : 'badge--danger'">{{ user.is_active ? '启用' : '停用' }}</span></td>
                <td><button class="btn btn-ghost btn-sm" type="button" :disabled="!!busy" @click="selectUser(user)">编辑</button></td>
              </tr></tbody>
            </table>
          </div>
          <PaginationBar :page="page" :page-size="pageSize" :has-next="page * pageSize < total" :loading="loading || !!busy" @change="load" />
        </template>
      </section>
    </div>

    <section v-if="selected" class="card edit-card">
      <div class="card-head"><div><h3 class="card-title">编辑账号：{{ selected.username }}</h3><p class="muted" style="margin: 4px 0 0">密码不会回显。重置密码不会注销已有会话；停用会在下次鉴权时拒绝，重新启用后未过期会话可恢复。</p></div><button class="btn btn-ghost btn-sm" type="button" :disabled="!!busy" @click="selected = null">关闭</button></div>
      <div class="edit-grid">
        <div class="field"><span class="field-label">角色</span><div class="role-checks"><label v-for="role in roles" :key="role" class="check-label"><input v-model="editRoles" type="checkbox" :value="role" :disabled="!!busy || roleDisabled(role)" />{{ roleName(role) }}</label></div><span class="field-hint">角色授权仍由服务端校验。</span></div>
        <div class="field"><span class="field-label">账号状态</span><p class="edit-status"><span class="badge" :class="selected.is_active ? 'badge--success' : 'badge--danger'">{{ selected.is_active ? '当前启用' : '当前停用' }}</span></p><button class="btn" :class="selected.is_active ? 'btn-danger' : 'btn-secondary'" type="button" :disabled="busy || cannotDisable" @click="toggleStatus">{{ selected.is_active ? '停用账号' : '重新启用' }}</button><span v-if="cannotDisable" class="field-hint">不能停用当前登录账号。</span></div>
        <div class="field"><label class="field-label" for="reset-password">设置新密码</label><input id="reset-password" v-model="resetPassword" :disabled="!!busy" type="password" autocomplete="new-password" placeholder="8–128 位，不会回显" /><button class="btn btn-danger" type="button" :disabled="!!busy" style="margin-top: 8px" @click="resetUserPassword"><span v-if="busy === 'reset'" class="spinner"></span>重置密码</button></div>
      </div>
      <div v-if="editError" class="form-error" role="alert">{{ editError }}</div>
      <div class="form-actions"><button class="btn btn-primary" type="button" :disabled="busy || !rolesValid" @click="saveRoles"><span v-if="busy === 'roles'" class="spinner"></span>保存角色</button></div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../api'
import { auth } from '../auth'
import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import PaginationBar from '../components/PaginationBar.vue'

const roles = ['ADMIN', 'ANALYST', 'REVIEWER', 'VIEWER']
const roleNames = { ADMIN: '管理员', ANALYST: '分析员', REVIEWER: '审核员', VIEWER: '查看员' }
const pageSize = 20
const users = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const busy = ref('')
const error = ref('')
const notice = ref('')
const createError = ref('')
const editError = ref('')
const selected = ref(null)
const editRoles = ref([])
const resetPassword = ref('')
const createForm = ref({ username: '', display_name: '', password: '', roles: [] })

const currentId = computed(() => auth.user?.id)
const cannotDisable = computed(() => selected.value && String(selected.value.id) === String(currentId.value))
const rolesValid = computed(() => editRoles.value.length > 0 && !(cannotRemoveOwnAdmin.value))
const cannotRemoveOwnAdmin = computed(() => cannotDisable.value && selected.value.roles.includes('ADMIN') && !editRoles.value.includes('ADMIN'))

function roleName(role) { return roleNames[role] || role }
function roleDisabled(role) { return cannotDisable.value && role === 'ADMIN' && selected.value.roles.includes('ADMIN') }
function validatePassword(value) { return typeof value === 'string' && value.length >= 8 && value.length <= 128 && value.trim().length > 0 }
function validateCreate() {
  const f = createForm.value
  if (!/^[A-Za-z0-9_.-]{3,64}$/.test(f.username)) return '用户名须为 3–64 位 ASCII 字母、数字、下划线、点或短横线。'
  const display = f.display_name.trim()
  if (display.length < 1 || display.length > 100) return '显示名称去除首尾空白后须为 1–100 个字符。'
  if (!validatePassword(f.password)) return '密码须为 8–128 位且不能全为空白。'
  if (!f.roles.length) return '至少选择一个角色。'
  return ''
}
function validateReset() { return validatePassword(resetPassword.value) ? '' : '密码须为 8–128 位且不能全为空白。' }

async function load(target = 1) {
  page.value = Math.max(1, Number(target) || 1); loading.value = true; error.value = ''
  try {
    const data = await apiFetch(`/users?page=${page.value}&page_size=${pageSize}`)
    users.value = data.items || []; total.value = data.total || 0
    if (page.value > 1 && !users.value.length && total.value) return load(page.value - 1)
    const refreshed = selected.value && users.value.find((u) => String(u.id) === String(selected.value.id))
    if (selected.value && refreshed) { selected.value = refreshed; editRoles.value = [...refreshed.roles] }
  } catch (e) { error.value = e.message; users.value = [] }
  finally { loading.value = false }
}
function selectUser(user) { if (busy.value) return; selected.value = user; editRoles.value = [...(user.roles || [])]; resetPassword.value = ''; editError.value = ''; notice.value = '' }
function clearMessages() { notice.value = ''; createError.value = ''; editError.value = '' }

async function createUser() {
  if (busy.value) return
  clearMessages(); const validation = validateCreate(); if (validation) { createError.value = validation; return }
  busy.value = 'create'
  try {
    await apiFetch('/users', { method: 'POST', body: JSON.stringify({ ...createForm.value, display_name: createForm.value.display_name.trim() }) })
    createForm.value = { username: '', display_name: '', password: '', roles: [] }; notice.value = '账号创建成功。'; await load(1)
  } catch (e) { createError.value = e.message } finally { busy.value = '' }
}
async function saveRoles() {
  if (busy.value) return
  clearMessages(); if (!rolesValid.value) { editError.value = cannotRemoveOwnAdmin.value ? '不能撤销当前登录账号的管理员角色。' : '至少选择一个角色。'; return }
  busy.value = 'roles'
  try { await apiFetch(`/users/${selected.value.id}/roles`, { method: 'PUT', body: JSON.stringify({ roles: editRoles.value }) }); notice.value = '角色保存成功。'; await load(page.value) }
  catch (e) { editError.value = e.message } finally { busy.value = '' }
}
async function toggleStatus() {
  if (busy.value || cannotDisable.value) return
  if (selected.value.is_active && !window.confirm('确定停用此账号吗？停用不会注销已有会话，但下次鉴权将被拒绝。')) return
  const targetId = selected.value.id
  const nextActive = !selected.value.is_active
  clearMessages(); busy.value = 'status'
  try { await apiFetch(`/users/${targetId}/status`, { method: 'PATCH', body: JSON.stringify({ is_active: nextActive }) }); notice.value = nextActive ? '账号已重新启用。' : '账号已停用。'; await load(page.value) }
  catch (e) { editError.value = e.message } finally { busy.value = '' }
}
async function resetUserPassword() {
  if (busy.value) return
  clearMessages(); const validation = validateReset(); if (validation) { editError.value = validation; return }
  if (!window.confirm('确定重置此账号密码吗？此操作不会注销已有会话。')) return
  busy.value = 'reset'
  try { await apiFetch(`/users/${selected.value.id}/reset-password`, { method: 'POST', body: JSON.stringify({ password: resetPassword.value }) }); resetPassword.value = ''; notice.value = '密码已重置，已有会话不会被注销。' }
  catch (e) { editError.value = e.message } finally { busy.value = '' }
}

onMounted(() => load(1))
</script>

<style scoped>
.users-layout { display: grid; grid-template-columns: minmax(260px, 0.8fr) minmax(0, 2fr); gap: var(--space-5); align-items: start; }
.users-layout .field { margin-bottom: var(--space-4); }
.users-table { min-width: 700px; }
.row-selected { background: var(--info-bg); }
.role-checks { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 4px; }
.check-label { display: inline-flex; align-items: center; gap: 5px; margin: 0; font-size: 13px; }
.check-label input { width: auto; }
.edit-card { margin-top: var(--space-5); }
.edit-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: var(--space-5); }
.edit-status { margin: 8px 0 10px; }
.form-error { color: var(--danger); font-size: 13px; margin-top: 10px; }
@media (max-width: 900px) { .users-layout, .edit-grid { grid-template-columns: 1fr; } }
</style>
