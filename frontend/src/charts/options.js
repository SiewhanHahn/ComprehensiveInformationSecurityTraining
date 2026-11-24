import { CHART, SIGNAL_COLORS, STATUS_COLORS, axisStyle, tooltipStyle } from './theme'

const BASE = {
  backgroundColor: 'transparent',
  animationDuration: 600,
  animationEasing: 'cubicOut',
  textStyle: { color: CHART.text }
}

export const STATUS_ORDER = [
  'DRAFT',
  'PENDING_REVIEW',
  'APPROVED',
  'PUBLISHED',
  'WITHDRAWN',
  'REJECTED'
]

export const STATUS_LABEL = {
  DRAFT: '草稿',
  PENDING_REVIEW: '待审核',
  APPROVED: '已批准',
  PUBLISHED: '已发布',
  WITHDRAWN: '已撤回',
  REJECTED: '已驳回'
}

const RISK_LABEL = {
  BLUE: '蓝色',
  YELLOW: '黄色',
  ORANGE: '橙色',
  RED: '红色'
}

const MODEL_COLORS = [CHART.cyan, CHART.blue, CHART.purple, CHART.yellow]

export function modelBar(models, { baseline = null, proxy = null, thresholdMm = null } = {}) {
  const values = models.map((m) => m.precipitation_mm)
  const numeric = values.filter((v) => v != null)
  const max = Math.max(...numeric, thresholdMm || 0, 1)

  const markLines = []
  if (baseline != null) {
    markLines.push({
      yAxis: baseline,
      label: { formatter: '基线', color: CHART.blue, fontSize: 10, position: 'insideEndTop' },
      lineStyle: { color: CHART.blue, type: 'dashed', width: 1 }
    })
  }
  if (proxy != null) {
    markLines.push({
      yAxis: proxy,
      label: { formatter: '代理标签', color: CHART.yellow, fontSize: 10, position: 'insideEndBottom' },
      lineStyle: { color: CHART.yellow, type: 'dotted', width: 1 }
    })
  }
  if (thresholdMm != null) {
    markLines.push({
      yAxis: thresholdMm,
      label: { formatter: '阈值', color: CHART.orange, fontSize: 10, position: 'insideEndBottom' },
      lineStyle: { color: CHART.orange, type: 'dashed', width: 1 }
    })
  }

  return {
    ...BASE,
    grid: { left: 8, right: 18, top: 34, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltipStyle,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(53,201,230,0.06)' } },
      valueFormatter: (v) => (v == null ? '缺测' : `${v} mm`)
    },
    xAxis: {
      type: 'category',
      data: models.map((m) => m.model),
      ...axisStyle({ splitLine: { show: false } })
    },
    yAxis: {
      type: 'value',
      name: 'mm',
      nameTextStyle: { color: CHART.faint, fontSize: 10 },
      min: 0,
      max: Math.ceil(max * 1.25),
      ...axisStyle()
    },
    series: [
      {
        type: 'bar',
        barWidth: 26,
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color: MODEL_COLORS[i % MODEL_COLORS.length],
            borderRadius: [3, 3, 0, 0]
          }
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          label: { position: 'insideEndTop', fontSize: 10 },
          data: markLines
        }
      }
    ]
  }
}

export function modelRadar(models) {
  const values = models.map((m) => m.precipitation_mm ?? 0)
  const max = Math.max(...values, 1) * 1.25
  return {
    ...BASE,
    tooltip: { ...tooltipStyle, trigger: 'item' },
    radar: {
      radius: '64%',
      center: ['50%', '55%'],
      indicator: models.map((m) => ({ name: m.model, max })),
      axisName: { color: CHART.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART.splitLine } },
      splitLine: { lineStyle: { color: CHART.splitLine } },
      splitArea: {
        areaStyle: { color: ['transparent', 'rgba(126,151,190,0.03)'] }
      }
    },
    series: [
      {
        type: 'radar',
        symbolSize: 5,
        lineStyle: { color: CHART.cyan, width: 2 },
        itemStyle: { color: CHART.cyan },
        areaStyle: { color: 'rgba(53,201,230,0.18)' },
        data: [{ value: values, name: '四模式降水' }]
      }
    ]
  }
}

export function baselineRadar(baseline, fusion) {
  const indicators = [
    { name: '精确率', max: 1 },
    { name: '召回率', max: 1 },
    { name: '误报抑制', max: 1 },
    { name: 'F1', max: 1 },
    { name: 'AUC', max: 1 }
  ]
  const pick = (b) => [
    b.precision,
    b.recall,
    Number((1 - b.fpr).toFixed(4)),
    b.f1,
    b.auc
  ]
  return {
    ...BASE,
    tooltip: { ...tooltipStyle, trigger: 'item' },
    legend: {
      bottom: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: CHART.muted, fontSize: 11 },
      data: ['基线 ECMWF', '四模式融合']
    },
    radar: {
      radius: '62%',
      center: ['50%', '50%'],
      indicator: indicators,
      axisName: { color: CHART.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART.splitLine } },
      splitLine: { lineStyle: { color: CHART.splitLine } },
      splitArea: {
        areaStyle: { color: ['transparent', 'rgba(126,151,190,0.03)'] }
      }
    },
    series: [
      {
        type: 'radar',
        symbolSize: 4,
        data: [
          {
            value: pick(baseline),
            name: '基线 ECMWF',
            lineStyle: { color: CHART.blue, type: 'dashed', width: 1.5 },
            itemStyle: { color: CHART.blue }
          },
          {
            value: pick(fusion),
            name: '四模式融合',
            lineStyle: { color: CHART.cyan, width: 2 },
            itemStyle: { color: CHART.cyan },
            areaStyle: { color: 'rgba(53,201,230,0.16)' }
          }
        ]
      }
    ]
  }
}

export function statusBar(counts) {
  const items = STATUS_ORDER.map((key) => ({
    key,
    label: STATUS_LABEL[key],
    count: counts[key] || 0
  }))
  return {
    ...BASE,
    grid: { left: 8, right: 30, top: 10, bottom: 8, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, ...axisStyle() },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.label),
      ...axisStyle({ splitLine: { show: false } })
    },
    series: [
      {
        type: 'bar',
        barWidth: 14,
        data: items.map((i) => ({
          value: i.count,
          itemStyle: {
            color: STATUS_COLORS[i.key],
            borderRadius: [0, 3, 3, 0]
          }
        })),
        label: {
          show: true,
          position: 'right',
          color: CHART.muted,
          fontSize: 11
        }
      }
    ]
  }
}

export function coverageBar(perCity, expected, nameOf) {
  const items = [...perCity]
    .sort((a, b) => a.model_count - b.model_count)
    .map((c) => ({
      label: nameOf(c.city_code),
      count: c.model_count
    }))
  return {
    ...BASE,
    grid: { left: 8, right: 30, top: 18, bottom: 8, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      max: expected,
      minInterval: 1,
      ...axisStyle()
    },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.label),
      ...axisStyle({ splitLine: { show: false } })
    },
    series: [
      {
        type: 'bar',
        barWidth: 13,
        data: items.map((i) => ({
          value: i.count,
          itemStyle: {
            color: i.count >= expected ? CHART.green : CHART.yellow,
            borderRadius: [0, 3, 3, 0]
          }
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          label: { formatter: `预期 ${expected}`, color: CHART.faint, fontSize: 10 },
          lineStyle: { color: CHART.faint, type: 'dashed', width: 1 },
          data: [{ xAxis: expected }]
        }
      }
    ]
  }
}

export function cityRiskBar(points) {
  return {
    ...BASE,
    grid: { top: 14, right: 44, bottom: 35, left: 66 },
    xAxis: { ...axisStyle, type: 'value', minInterval: 1 },
    yAxis: { ...axisStyle, type: 'category', inverse: true, data: points.map(point => point.name) },
    tooltip: {
      ...tooltipStyle,
      trigger: 'item',
      renderMode: 'richText',
      formatter: ({ name, value, data }) => `${name}\n暴雨记录：${value} 条\n最高教学信号：${RISK_LABEL[data.risk] || '无'}`
    },
    series: [{
      type: 'bar',
      name: '暴雨记录',
      barMaxWidth: 21,
      label: { show: true, position: 'right', color: CHART.text },
      data: points.map(({ count, risk }) => ({ value: count, risk, itemStyle: { color: SIGNAL_COLORS[risk] || CHART.cyan } }))
    }]
  }
}
