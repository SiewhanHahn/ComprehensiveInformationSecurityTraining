<template>
  <details class="version-history">
    <summary>历史版本</summary>
    <div class="history-content">
      <label class="field">
        <span class="field-label">版本号</span>
        <select :value="selectedVersion" @change="selectVersion($event.target.value)">
          <option v-for="version in currentVersion" :key="version" :value="version">
            第 {{ version }} 版{{ version === currentVersion ? '（当前）' : '' }}
          </option>
        </select>
      </label>

      <div class="muted" role="status">
        <p v-if="currentVersion === 1">这是第 1 版，没有更早的版本。</p>
        <p v-else-if="state === 'loading'">正在加载第 {{ selectedVersion }} 版…</p>
        <p v-else-if="state === 'not-retained'">第 {{ selectedVersion }} 版的旧版正文未留存。</p>
        <p v-else-if="state === 'not-found'">预警或版本不可用，请返回列表确认预警是否仍可见。</p>
      </div>
      <div v-if="state === 'error'">
        <p role="alert">加载版本失败：{{ error }}</p>
        <button class="btn btn-ghost btn-sm" type="button" @click="retryVersion">重试</button>
      </div>

      <dl v-if="body" class="version-body">
        <dt class="detail-label">标题</dt>
        <dd>{{ body.title }}</dd>
        <dt class="detail-label">影响区域</dt>
        <dd>{{ body.area_text }}</dd>
        <dt class="detail-label">影响说明</dt>
        <dd>{{ body.impact_text ?? '—' }}</dd>
        <dt class="detail-label">研判依据</dt>
        <dd>{{ body.reasoning_text }}</dd>
      </dl>
    </div>
  </details>
</template>

<script setup>
import { computed, onScopeDispose, ref, watch } from 'vue'
import { apiFetch } from '../api'

const props = defineProps({ warning: { type: Object, required: true } })
const currentVersion = computed(() => props.warning.version_no)
const selectedVersion = ref(currentVersion.value)
const snapshot = ref(null)
const state = ref('idle')
const error = ref('')
const body = computed(() => selectedVersion.value === currentVersion.value ? props.warning : snapshot.value)
let requestSequence = 0

function resetRequest() {
  requestSequence++
  snapshot.value = null
  state.value = 'idle'
  error.value = ''
}

watch([() => props.warning.public_id, currentVersion], () => {
  resetRequest()
  selectedVersion.value = currentVersion.value
}, { flush: 'sync' })

onScopeDispose(() => { requestSequence++ })

function selectVersion(value) {
  const version = Number(value)
  if (!Number.isInteger(version) || version < 1 || version > currentVersion.value || version === selectedVersion.value) return
  selectedVersion.value = version
  return loadSelectedVersion()
}

function retryVersion() {
  if (state.value === 'error') return loadSelectedVersion()
}

async function loadSelectedVersion() {
  resetRequest()
  const version = selectedVersion.value
  if (version === currentVersion.value) return

  // 用请求序号区分同一张单上“第 1 版 → 第 2 版 → 第 1 版”的两次请求。
  const request = requestSequence
  const id = encodeURIComponent(props.warning.public_id)
  state.value = 'loading'
  try {
    const result = await apiFetch(`/warnings/${id}/versions/${version}`)
    if (request !== requestSequence) return
    snapshot.value = result
    state.value = 'idle'
  } catch (e) {
    if (request !== requestSequence) return
    if (e?.status === 404) {
      state.value = e.code === 'VERSION_NOT_RETAINED' ? 'not-retained' : 'not-found'
    } else {
      error.value = e?.message || '请稍后重试。'
      state.value = 'error'
    }
  }
}
</script>

<style scoped>
.version-history {
  margin-top: var(--space-4);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

summary {
  color: var(--color-primary);
  cursor: pointer;
  font-weight: 600;
}

.history-content {
  margin-top: var(--space-3);
}

.field {
  width: fit-content;
  max-width: 100%;
}

.version-body dd {
  margin: 0 0 var(--space-3);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.version-body dd:last-child {
  margin-bottom: 0;
}
</style>
