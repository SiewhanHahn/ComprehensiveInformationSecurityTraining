<template>
  <div class="empty-state" :class="{ 'empty-state--compact': compact }">
    <svg class="empty-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 8.5 12 4l8 4.5v9L12 22l-8-4.5v-9Z"
        stroke="currentColor"
        stroke-width="1.4"
        stroke-linejoin="round"
      />
      <path d="M4 8.5 12 13l8-4.5M12 13v9" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" />
    </svg>
    <div class="empty-title">{{ title }}</div>
    <div v-if="description" class="empty-desc">{{ description }}</div>
    <div v-if="$slots.default" style="margin-top: 8px">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  compact: { type: Boolean, default: false }
})
</script>
