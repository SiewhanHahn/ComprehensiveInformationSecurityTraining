<template>
  <Transition name="badge" mode="out-in">
    <span
      :key="String(value)"
      class="badge"
      :class="[`badge--${tone}`, size === 'sm' ? 'badge--sm' : '']"
      :title="value == null ? '' : String(value)"
    >
      <span
        v-if="dot"
        class="badge-dot"
        :class="{ 'badge-dot--pulse': pulse }"
        aria-hidden="true"
      ></span>
      {{ label }}
    </span>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import {
  WARNING_STATUS,
  RISK_LEVEL,
  FEEDBACK_STATUS,
  AUDIT_RESULT,
  AUDIT_ACTION,
  DATA_STATUS,
  getMeta
} from '../ui/labels'

const props = defineProps({
  value: { type: String, default: null },
  kind: {
    type: String,
    default: 'warningStatus',
    validator: (v) =>
      ['warningStatus', 'risk', 'feedback', 'auditResult', 'auditAction', 'dataStatus'].includes(v)
  },
  size: { type: String, default: 'md' },
  dot: { type: Boolean, default: false }
})

const MAPS = {
  warningStatus: WARNING_STATUS,
  risk: RISK_LEVEL,
  feedback: FEEDBACK_STATUS,
  auditResult: AUDIT_RESULT,
  auditAction: AUDIT_ACTION,
  dataStatus: DATA_STATUS
}

const meta = computed(() => {
  if (props.kind === 'risk' && (props.value === null || props.value === undefined || props.value === '')) {
    return { label: '未达阈值', tone: 'neutral' }
  }
  return getMeta(MAPS[props.kind] || {}, props.value)
})
const label = computed(() => meta.value?.label || '—')
const tone = computed(() => meta.value?.tone || 'neutral')
const pulse = computed(
  () => props.dot && (props.value === 'PENDING_REVIEW' || props.value === 'PROCESSING')
)
</script>
