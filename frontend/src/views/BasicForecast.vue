<template>
  <div class="page">
    <header class="page-head">
      <div class="page-heading">
        <h2 class="page-title">基础预测</h2>
        <span class="page-subtitle">自填输入 · 教学试算 · 不创建或发布预警</span>
      </div>
      <router-link class="btn btn-ghost btn-sm" to="/hazards">查看灾种覆盖</router-link>
    </header>
    <DroughtTrial />
  </div>
</template>

<script setup>
import DroughtTrial from '../components/DroughtTrial.vue'
</script>
