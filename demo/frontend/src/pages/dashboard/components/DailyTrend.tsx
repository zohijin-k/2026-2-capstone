import { useMemo, useState } from 'react'
import { baseOption, categoryAxis, HOVER_SHADOW, tooltipRow, tooltipTitle, valueAxis } from '../charts/base'
import { formatDate } from '../lib/dates'
import { fmtInt } from '../lib/format'
import type { DailyPoint } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'
import { Segmented } from './Segmented'

type Mode = 'daily' | 'cumulative'

const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: 'daily', label: '일별' },
  { value: 'cumulative', label: '누적' },
]

interface DailyTrendProps {
  daily: DailyPoint[]
  quota: number
  scopeLabel: string
  tokens: ChartTokens
  className?: string
}

export function DailyTrend({ daily, quota, scopeLabel, tokens, className }: DailyTrendProps) {
  const [mode, setMode] = useState<Mode>('daily')

  const option = useMemo(() => {
    const base = baseOption(tokens)
    const cumulative = mode === 'cumulative'
    const seriesName = cumulative ? '누적 접수' : '일별 접수'
    const data = daily.map((point) => (cumulative ? point.cumulativeSubmitted : point.submitted))

    return {
      ...base,
      grid: { left: 4, right: 12, top: 16, bottom: 0, containLabel: true },
      tooltip: {
        ...base.tooltip,
        trigger: 'axis',
        axisPointer: cumulative
          ? { type: 'line', lineStyle: { color: tokens.axis } }
          : { type: 'shadow', shadowStyle: { color: HOVER_SHADOW } },
        formatter: (params: unknown) => {
          const [item] = params as { axisValueLabel: string; value: number | null }[]
          if (!item) return ''
          return (
            tooltipTitle(item.axisValueLabel) +
            tooltipRow(tokens.series1, seriesName, item.value == null ? '—' : `${fmtInt(item.value)}건`)
          )
        },
      },
      xAxis: categoryAxis(
        tokens,
        daily.map((point) => formatDate(point.date)),
        { boundaryGap: !cumulative },
      ),
      yAxis: valueAxis(tokens),
      series: [
        cumulative
          ? {
              name: seriesName,
              type: 'line',
              data,
              showSymbol: false,
              symbolSize: 8,
              lineStyle: { width: 2, color: tokens.series1 },
              itemStyle: { color: tokens.series1, borderColor: tokens.surface, borderWidth: 2 },
              areaStyle: { color: tokens.series1, opacity: 0.08 },
              markLine: {
                silent: true,
                symbol: 'none',
                data: [{ yAxis: quota }],
                lineStyle: { color: tokens.muted, width: 1, type: 'solid' },
                label: { formatter: `정원 ${fmtInt(quota)}명`, color: tokens.textSecondary, fontSize: 11, position: 'insideStartTop' },
              },
            }
          : {
              name: seriesName,
              type: 'bar',
              data,
              barMaxWidth: 28,
              itemStyle: { color: tokens.series1, borderRadius: [4, 4, 0, 0] },
            },
      ],
    }
  }, [daily, quota, tokens, mode])

  return (
    <Card
      className={className}
      title="접수 추이"
      subtitle={`${scopeLabel} · 제출 완료(접수) 건수 · 신청기간 3.3(화)~3.16(월)`}
      actions={<Segmented options={MODE_OPTIONS} value={mode} onChange={setMode} ariaLabel="집계 방식" />}
    >
      <Chart key={mode} option={option} height={400} ariaLabel={`${scopeLabel} ${mode === 'daily' ? '일별' : '누적'} 접수 추이`} />
    </Card>
  )
}
