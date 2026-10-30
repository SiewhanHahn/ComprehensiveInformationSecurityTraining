import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  BarChart,
  EffectScatterChart,
  LineChart,
  RadarChart,
  ScatterChart
} from 'echarts/charts'
import {
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent
} from 'echarts/components'

echarts.use([
  CanvasRenderer,
  BarChart,
  LineChart,
  RadarChart,
  EffectScatterChart,
  ScatterChart,
  GridComponent,
  RadarComponent,
  LegendComponent,
  TooltipComponent,
  GeoComponent,
  MarkLineComponent
])

export default echarts
