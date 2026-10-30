<template>
  <div class="chart-panel">
    <div v-if="title || subtitle" class="chart-panel-head">
      <span class="chart-panel-title">{{ title }}</span>
      <span v-if="subtitle" class="chart-panel-sub">{{ subtitle }}</span>
    </div>
    <span v-if="sweep && ready && option" class="map-sweep" aria-hidden="true"></span>
    <div
      ref="host"
      class="chart-body"
      role="img"
      :aria-label="ariaLabel || title || '数据图表'"
      :style="{ height: option && !failed ? height + 'px' : '0px' }"
    ></div>
    <div v-if="!option || failed" class="chart-empty">
      {{ failed ? '图表加载失败，请刷新重试' : emptyText || '暂无可展示的数据' }}
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  option: { type: Object, default: null },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  height: { type: Number, default: 320 },
  emptyText: { type: String, default: '' },
  ariaLabel: { type: String, default: '' },
  sweep: { type: Boolean, default: false }
})

const host = ref(null)
const ready = ref(false)
const failed = ref(false)

let chart = null
let observer = null
let echartsLib = null
let disposed = false

async function ensureChart() {
  if (chart || !host.value) return chart
  const [{ default: echarts }, { ensureChinaMap }] = await Promise.all([
    import('../lib/echarts'),
    import('../lib/chinaMap')
  ])
  if (props.option?.geo?.map === 'china') {
    await ensureChinaMap()
  }
  if (disposed) return null
  echartsLib = echarts
  chart = echarts.init(host.value, null, { renderer: 'canvas' })
  ready.value = true
  observer = new ResizeObserver(() => chart && chart.resize())
  observer.observe(host.value)
  return chart
}

async function render() {
  if (!props.option) return
  try {
    await nextTick()
    const instance = await ensureChart()
    if (!instance) return
    instance.setOption(props.option, { notMerge: true })
    instance.resize()
  } catch (e) {
    failed.value = true
  }
}

onMounted(() => {
  nextTick(render)
})

watch(
  () => props.option,
  () => {
    failed.value = false
    render()
  }
)

onBeforeUnmount(() => {
  disposed = true
  if (observer) observer.disconnect()
  if (chart && echartsLib) {
    chart.dispose()
    chart = null
  }
})
</script>
