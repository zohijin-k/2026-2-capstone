import { useMemo } from 'react'
import { baseOption, categoryAxis, HOVER_SHADOW, legendOption, tooltipRow, tooltipTitle, valueAxis } from '../charts/base'
import type { RegionName } from '../data/types'
import { fmtInt, fmtPct } from '../lib/format'
import type { RegionRow } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'

interface StageDefinition {
  key: 'waiting' | 'reviewing' | 'eligible' | 'rejected'
  label: string
  color: (tokens: ChartTokens) => string
}

const STAGES: StageDefinition[] = [
  { key: 'waiting', label: '서류확인 대기', color: (tokens) => tokens.neutral },
  { key: 'reviewing', label: '자격심사 중', color: (tokens) => tokens.ordinal[0] },
  { key: 'eligible', label: '적합', color: (tokens) => tokens.ordinal[2] },
  { key: 'rejected', label: '부적합', color: (tokens) => tokens.series2 },
]

interface ReviewStagesProps {
  rows: RegionRow[]
  selected: RegionName | null
  onSelect: (region: RegionName | null) => void
  tokens: ChartTokens
  className?: string
}

export function ReviewStages({ rows, selected, onSelect, tokens, className }: ReviewStagesProps) {
  const option = useMemo(() => {
    const base = baseOption(tokens)
    return {
      ...base,
      legend: legendOption(tokens),
      grid: { left: 4, right: 16, top: 36, bottom: 0, containLabel: true },
      tooltip: {
        ...base.tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: HOVER_SHADOW } },
        formatter: (params: unknown) => {
          const items = params as { dataIndex: number }[]
          const row = rows[items[0]?.dataIndex ?? -1]
          if (!row) return ''
          return (
            tooltipTitle(`${row.name} · 접수 ${fmtInt(row.submitted)}건`) +
            STAGES.map((stage) =>
              tooltipRow(
                stage.color(tokens),
                stage.label,
                `${fmtInt(row[stage.key])}건 · ${row.submitted ? fmtPct(row[stage.key] / row.submitted, 0) : '—'}`,
              ),
            ).join('')
          )
        },
      },
      xAxis: valueAxis(tokens, {
        max: 100,
        axisLabel: { color: tokens.muted, fontSize: 11, formatter: '{value}%' },
      }),
      yAxis: categoryAxis(
        tokens,
        rows.map((row) => row.name),
        {
          inverse: true,
          axisLine: { show: false },
          axisLabel: {
            color: tokens.textSecondary,
            fontSize: 12,
            formatter: (value: string) => (value === selected ? `{selected|${value}}` : value),
            rich: { selected: { fontWeight: 'bold', color: tokens.textPrimary, fontSize: 12 } },
          },
        },
      ),
      series: STAGES.map((stage) => ({
        name: stage.label,
        type: 'bar',
        stack: 'stages',
        barWidth: 14,
        cursor: 'pointer',
        itemStyle: { color: stage.color(tokens), borderColor: tokens.surface, borderWidth: 1 },
        data: rows.map((row) => (row.submitted ? (row[stage.key] / row.submitted) * 100 : 0)),
      })),
    }
  }, [rows, selected, tokens])

  return (
    <Card className={className} title="시군별 심사 진행" subtitle="접수 건 대비 단계별 비율 · 전체 시군 · 막대를 클릭하면 시군 선택">
      <Chart
        option={option}
        height={400}
        ariaLabel="시군별 심사 단계 비율 누적 막대"
        onClick={(params) => {
          if (!params.name) return
          const name = params.name as RegionName
          onSelect(name === selected ? null : name)
        }}
      />
    </Card>
  )
}
