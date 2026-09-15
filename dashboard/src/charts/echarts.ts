import { BarChart, LineChart, MapChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import jeonbukGeo from '../data/jeonbuk.geo.json'

echarts.use([
  BarChart,
  LineChart,
  MapChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

/** 통계청 2013 시군구 경계에서 전북 14개 시군만 추출 (전주 완산·덕진구 병합) */
echarts.registerMap('jeonbuk', jeonbukGeo as unknown as Parameters<typeof echarts.registerMap>[1])

export { echarts }
export type { EChartsCoreOption as ChartOption } from 'echarts/core'
