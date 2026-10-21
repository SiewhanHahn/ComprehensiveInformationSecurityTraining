<template>
  <div class="page">
    <div class="card">
      <EmptyState
        title="页面不存在"
        description="你访问的地址可能已被移动或从未存在。"
      >
        <router-link class="btn btn-primary btn-sm" to="/">返回总览</router-link>
      </EmptyState>
    </div>
  </div>
</template>

<script setup>
import EmptyState from '../components/EmptyState.vue'
</script>
