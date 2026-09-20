import { useMemo, useState } from 'react'
import { baseOption } from '../charts/base'
import type { RegionName } from '../data/types'
import { fmtDays, fmtInt, fmtPct, fmtRatio } from '../lib/format'
import type { RegionRow } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'
import { Segmented } from './Segmented'

type MetricKey = 'submitted' | 'competition' | 'progress' | 'avgDays'

const METRICS: Record<MetricKey, { label: string; value: (row: RegionRow) => number | null; format: (v: number) => string }> = {
  submitted: { label: '신청자 수', value: (row) => row.submitted, format: (v) => `${fmtInt(v)}명` },
  competition: { label: '경쟁률', value: (row) => (row.submitted ? row.competition : null), format: fmtRatio },
  progress: { label: '심사 진행률', value: (row) => (row.submitted ? row.progress : null), format: (v) => fmtPct(v, 0) },
  avgDays: { label: '평균 처리기간', value: (row) => row.avgProcessingDays, format: fmtDays },
}

const METRIC_OPTIONS = (Object.keys(METRICS) as MetricKey[]).map((key) => ({ value: key, label: METRICS[key].label }))

interface JeonbukMapProps {
  rows: RegionRow[]
  selected: RegionName | null
  onSelect: (region: RegionName | null) => void
  tokens: ChartTokens
  className?: string
}

export function JeonbukMap({ rows, selected, onSelect, tokens, className }: JeonbukMapProps) {
  const [metricKey, setMetricKey] = useState<MetricKey>('submitted')
  const metric = METRICS[metricKey]

  const option = useMemo(() => {
    const base = baseOption(tokens)
    const values = rows.map(metric.value).filter((value): value is number => value !== null)
    const min = values.length ? Math.min(...values) : 0
    const max = values.length ? Math.max(...values) : 1
    const byName = new Map(rows.map((row) => [row.name as string, row]))

    return {
      ...base,
      tooltip: {
        ...base.tooltip,
        trigger: 'item',
        formatter: (params: unknown) => {
          const { name } = params as { name: string }
          const row = byName.get(name)
          if (!row) return name
          const value = metric.value(row)
          return (
            `<div style="font-weight:600;margin-bottom:4px">${row.name}</div>` +
            `${metric.label} <b>${value === null ? '—' : metric.format(value)}</b><br/>` +
            `<span style="color:${tokens.textSecondary}">정원 ${fmtInt(row.quota)}명 · 접수 ${fmtInt(row.submitted)}명</span>`
          )
        },
      },
      visualMap: {
        type: 'continuous',
        min,
        max: max === min ? min + 1 : max,
        orient: 'horizontal',
        left: 0,
        bottom: 0,
        itemWidth: 10,
        itemHeight: 140,
        calculable: false,
        text: [metric.format(max), metric.format(min)],
        textGap: 8,
        textStyle: { color: tokens.textSecondary, fontSize: 11 },
        inRange: { color: tokens.sequential },
      },
      series: [
        {
          type: 'map',
          map: 'jeonbuk',
          roam: false,
          selectedMode: false,
          layoutCenter: ['50%', '46%'],
          layoutSize: '96%',
          emphasis: { disabled: true },
          label: {
            show: true,
            fontSize: 11,
            color: tokens.textPrimary,
            textBorderColor: tokens.surface,
            textBorderWidth: 2.5,
          },
          itemStyle: { areaColor: tokens.grid, borderColor: tokens.surface, borderWidth: 1 },
          data: rows.map((row) => {
            const value = metric.value(row)
            const isSelected = row.name === selected
            return {
              name: row.name,
              value: value ?? Number.NaN,
              itemStyle: isSelected ? { borderColor: tokens.textPrimary, borderWidth: 2.5 } : {},
              label: isSelected ? { fontWeight: 'bold', fontSize: 13 } : {},
            }
          }),
        },
      ],
    }
  }, [rows, selected, tokens, metric])

  return (
    <Card
      className={className}
      title="시군별 현황"
      subtitle="전체 시군 기준 · 시군을 클릭하면 필터가 적용됩니다"
      actions={<Segmented options={METRIC_OPTIONS} value={metricKey} onChange={setMetricKey} ariaLabel="지도 지표" />}
    >
      <Chart
        option={option}
        height={400}
        ariaLabel={`전북 14개 시군 ${metric.label} 지도`}
        onClick={(params) => {
          if (!params.name) return
          const name = params.name as RegionName
          onSelect(name === selected ? null : name)
        }}
      />
    </Card>
  )
}
