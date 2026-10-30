// 图表暗色主题常量，与 style.css 信号色保持一致
export const CHART = {
  text: '#e8edf5',
  muted: '#93a1b3',
  faint: '#6e7c8e',
  axisLine: 'rgba(126, 151, 190, 0.22)',
  splitLine: 'rgba(126, 151, 190, 0.10)',
  tooltipBg: '#111f36',
  tooltipBorder: 'rgba(126, 151, 190, 0.35)',
  cyan: '#35c9e6',
  blue: '#58a6ff',
  yellow: '#e8b53d',
  orange: '#ff8b3d',
  red: '#f05a50',
  green: '#3fca8d',
  purple: '#9d7bff',
  mapArea: '#14223a',
  mapBorder: 'rgba(88, 166, 255, 0.35)'
}

export const SIGNAL_COLORS = {
  BLUE: CHART.blue,
  YELLOW: CHART.yellow,
  ORANGE: CHART.orange,
  RED: CHART.red
}

export const STATUS_COLORS = {
  DRAFT: CHART.muted,
  PENDING_REVIEW: CHART.yellow,
  APPROVED: CHART.cyan,
  PUBLISHED: CHART.green,
  WITHDRAWN: CHART.faint,
  REJECTED: CHART.red
}

export const tooltipStyle = {
  backgroundColor: CHART.tooltipBg,
  borderColor: CHART.tooltipBorder,
  borderWidth: 1,
  padding: [8, 12],
  textStyle: { color: CHART.text, fontSize: 12 }
}

export function axisStyle(extra = {}) {
  return {
    axisLine: { lineStyle: { color: CHART.axisLine } },
    axisTick: { show: false },
    axisLabel: { color: CHART.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: CHART.splitLine } },
    ...extra
  }
}
