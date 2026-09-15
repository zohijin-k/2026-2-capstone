import type { ChartOption } from '../charts/echarts'
import { useECharts, type ChartClickParams } from '../hooks/useECharts'

interface ChartProps {
  option: ChartOption
  height: number
  ariaLabel: string
  onClick?: (params: ChartClickParams) => void
}

export function Chart({ option, height, ariaLabel, onClick }: ChartProps) {
  const containerRef = useECharts(option, onClick)
  return <div ref={containerRef} className="chart" style={{ height }} role="img" aria-label={ariaLabel} />
}
