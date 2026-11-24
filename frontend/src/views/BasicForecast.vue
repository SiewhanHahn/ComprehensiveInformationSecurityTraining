<template>
  <div class="page">
    <header class="page-head">
      <div class="page-heading">
        <h2 class="page-title">基础预测</h2>
        <span class="page-subtitle">自填输入 · 教学试算 · 不创建或发布预警</span>
      </div>
      <router-link class="btn btn-ghost btn-sm" to="/hazards">查看灾种覆盖</router-link>
    </header>
    <nav class="basic-trials" aria-label="基础预测灾种">
      <router-link v-for="trial in trials" :key="trial.key" :to="trial.to" custom v-slot="{ href, navigate }">
        <a :href="href" class="btn btn-sm" :class="trial === selectedTrial ? 'btn-primary' : 'btn-ghost'"
           :aria-current="trial === selectedTrial ? 'page' : undefined" @click="navigate">{{ trial.label }}</a>
      </router-link>
    </nav>
    <component :is="selectedTrial.component" :key="selectedTrial.key" v-bind="selectedTrial.props" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DroughtTrial from '../components/DroughtTrial.vue'
import HourlyTemperatureTrial from '../components/HourlyTemperatureTrial.vue'

const route = useRoute()
const trials = [
  { key: 'drought', label: '干旱', to: '/basic-forecast', component: DroughtTrial },
  { key: 'heat', label: '高温', to: '/basic-forecast?hazard=heat', component: HourlyTemperatureTrial },
  { key: 'cold', label: '低温', to: '/basic-forecast?hazard=cold', component: HourlyTemperatureTrial, props: { mode: 'cold' } }
]
const selectedTrial = computed(() => trials.find(trial => trial.key === route.query.hazard) ?? trials[0])
</script>

<style scoped>
.basic-trials { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
</style>
