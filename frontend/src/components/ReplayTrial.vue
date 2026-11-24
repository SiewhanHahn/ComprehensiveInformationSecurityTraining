<template>
  <section class="card" aria-labelledby="trial-heading">
    <div class="card-head">
      <h3 id="trial-heading" class="card-title">外部城市降水试算</h3>
      <span class="card-subtitle">不保存文件，不创建预警，不计入九城实验</span>
    </div>
    <p>每行是一个城市的一个 UTC 日，提供提前 24 小时的四路累计降水（mm）。只有实测雨量不能做四模式融合。</p>
    <p class="trial-links">
      <a href="/trial/template.json" download>下载填写模板</a>
      <a href="/trial/nanjing.json" download>南京样例 · 2026-10-01 至 10-07</a>
      <a href="/trial/nanjing-source.json" download>样例来源与获取时间</a>
      <a href="/trial/missing-model.json" download>缺一列示例</a>
    </p>
    <form class="trial-controls" @submit.prevent="run">
      <div class="field"><label class="field-label" for="trial-file">UTF-8 JSON · 最多 200 行 / 256 KiB</label>
        <input id="trial-file" type="file" accept=".json,application/json" @change="selectFile($event.target.files[0])" /></div>
      <div class="field"><label class="field-label" for="trial-threshold">比较阈值</label>
        <select id="trial-threshold" v-model="threshold" @change="reset">
          <option value="MODERATE">10 mm/24h</option><option value="HEAVY">25 mm/24h</option><option value="STORM">50 mm/24h</option>
        </select></div>
      <button type="submit" class="btn btn-primary" :disabled="!file || busy">{{ busy ? '计算中…' : '运行试算' }}</button>
    </form>
    <p v-if="error" role="alert" class="alert alert--error">{{ error }}</p>
    <div v-if="result" class="table-wrap">
      <table class="table"><caption>共 {{ result.rows.length }} 条 · 达标为 ≥ {{ result.threshold_mm }} mm；参考值不参与计算</caption>
        <thead><tr><th>城市 / UTC 日期</th><th>ECMWF 基线</th><th>GFS</th><th>ICON</th><th>GEM</th><th>四路均值</th><th>事后参考</th></tr></thead>
        <tbody><tr v-for="r in result.rows" :key="JSON.stringify([r.city, r.valid_date])">
          <th scope="row">{{ r.city }} · {{ r.valid_date }}</th>
          <td>{{ r.baseline_mm }} · {{ hit(r.baseline_hit) }}</td><td>{{ r.models.gfs_global }}</td><td>{{ r.models.icon_global }}</td><td>{{ r.models.gem_global }}</td>
          <td class="cell-accent">{{ r.fused_mm }} · {{ hit(r.fusion_hit) }}</td>
          <td>{{ r.reference_mm == null ? '未提供' : `${r.reference_mm} · ${hit(r.reference_hit)}（${r.reference_type === 'ERA5_PROXY' ? 'ERA5 再分析' : '文件声明的站点实测'}）` }}</td>
        </tr></tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { apiFetch } from '../api'

const threshold = ref('HEAVY'), file = ref(null), result = ref(null), busy = ref(false), error = ref('')
let revision = 0
const hit = value => value ? '达标' : '未达'
function reset() {
  revision++
  result.value = null
  error.value = ''
  busy.value = false
}
function selectFile(value) {
  reset()
  file.value = value || null
  if (value && value.size > 256 * 1024) {
    file.value = null
    error.value = '文件超过 256 KiB，请拆分批次。'
  }
}
async function run() {
  if (!file.value || busy.value) return
  reset()
  const id = revision
  busy.value = true
  try {
    const body = await file.value.arrayBuffer()
    if (id !== revision) return
    const data = await apiFetch(`/replay/trial?threshold_code=${threshold.value}`, { method: 'POST', body })
    if (id === revision) result.value = data
  } catch (e) {
    if (id === revision) error.value = e.message || '试算未完成，请重新选择文件。'
  } finally {
    if (id === revision) busy.value = false
  }
}
</script>

<style scoped>
.trial-links, .trial-controls { display: flex; align-items: end; flex-wrap: wrap; gap: 10px 20px; margin: 16px 0; }
.trial-controls input { max-width: 100%; }
caption { text-align: left; padding: 10px 0; }
</style>
