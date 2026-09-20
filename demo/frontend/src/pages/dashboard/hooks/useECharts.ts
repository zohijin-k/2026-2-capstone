import { useEffect, useRef } from 'react'
import { echarts, type ChartOption } from '../charts/echarts'

export interface ChartClickParams {
  name?: string
  seriesName?: string
  dataIndex?: number
}

/** ECharts 인스턴스를 컨테이너 크기에 맞춰 유지하고 option 변경을 반영 */
export function useECharts(option: ChartOption, onClick?: (params: ChartClickParams) => void) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null)
  const clickRef = useRef(onClick)

  useEffect(() => {
    clickRef.current = onClick
  }, [onClick])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const chart = echarts.init(container, null, { renderer: 'canvas' })
    chartRef.current = chart
    chart.on('click', (params) => clickRef.current?.(params as ChartClickParams))
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(container)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, { lazyUpdate: true })
  }, [option])

  return containerRef
}
