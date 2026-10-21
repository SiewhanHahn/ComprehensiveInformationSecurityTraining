<template>
  <div class="pagination">
    <div class="pagination-info" aria-live="polite">
      第 {{ page }} 页 · 每页 {{ pageSize }} 条
    </div>
    <div class="pagination-controls">
      <button
        class="pagination-btn"
        type="button"
        :disabled="loading || page <= 1"
        aria-label="上一页"
        @click="$emit('change', page - 1)"
      >
        上一页
      </button>
      <span class="pagination-page">{{ page }}</span>
      <button
        class="pagination-btn"
        type="button"
        :disabled="loading || !hasNext"
        aria-label="下一页"
        @click="$emit('change', page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
  hasNext: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})

defineEmits(['change'])
</script>
