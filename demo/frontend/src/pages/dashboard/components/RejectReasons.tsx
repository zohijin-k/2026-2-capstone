import { useMemo } from 'react'
import { baseOption, categoryAxis, tooltipRow, tooltipTitle, valueAxis } from '../charts/base'
import type { RejectStage } from '../data/types'
import { fmtInt, fmtPct } from '../lib/format'
import type { RejectReasonItem } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'

const STAGE_TAG: Record<RejectStage, string> = {
  document: '서류',
  eligibility: '자격',
  duplicate: '2차',
}

const MAX_ITEMS = 10
const HEIGHT = 400

interface RejectReasonsProps {
  reasons: RejectReasonItem[]
  scopeLabel: string
  tokens: ChartTokens
  className?: string
}

export function RejectReasons({ reasons, scopeLabel, tokens, className }: RejectReasonsProps) {
  const total = reasons.reduce((sum, item) => sum + item.count, 0)
  const items = reasons.slice(0, MAX_ITEMS)

  const option = useMemo(() => {
    const base = baseOption(tokens)
    return {
      ...base,
      grid: { left: 4, right: 96, top: 4, bottom: 0, containLabel: true },
      tooltip: {
        ...base.tooltip,
        trigger: 'item',
        formatter: (params: unknown) => {
          const { dataIndex } = params as { dataIndex: number }
          const item = items[dataIndex]
          if (!item) return ''
          return (
            tooltipTitle(`[${STAGE_TAG[item.stage]}] ${item.reason}`) +
            tooltipRow(tokens.series2, '부적합', `${fmtInt(item.count)}건 · ${fmtPct(item.count / total, 1)}`)
          )
        },
      },
      xAxis: valueAxis(tokens, { splitNumber: 3 }),
      yAxis: categoryAxis(
        tokens,
        items.map((item) => `{tag|${STAGE_TAG[item.stage]}} ${item.reason}`),
        {
          inverse: true,
          axisLine: { show: false },
          axisLabel: {
            color: tokens.textSecondary,
            fontSize: 12,
            rich: {
              tag: {
                color: tokens.muted,
                fontSize: 11,
                backgroundColor: tokens.grid,
                borderRadius: 3,
                padding: [2, 4],
              },
            },
          },
        },
      ),
      series: [
        {
          name: '부적합',
          type: 'bar',
          barWidth: 14,
          data: items.map((item) => item.count),
          itemStyle: { color: tokens.series2, borderRadius: [0, 4, 4, 0] },
          label: {
            show: true,
            position: 'right',
            color: tokens.textSecondary,
            fontSize: 11,
            formatter: (params: unknown) => {
              const { value } = params as { value: number }
              return `${fmtInt(value)}건 · ${fmtPct(value / total, 0)}`
            },
          },
        },
      ],
    }
  }, [items, total, tokens])

  return (
    <Card className={className} title="부적합 사유" subtitle={`${scopeLabel} · 누적 ${fmtInt(total)}건 · 상위 ${Math.min(MAX_ITEMS, items.length)}개`}>
      {items.length ? (
        <Chart option={option} height={HEIGHT} ariaLabel={`${scopeLabel} 부적합 사유별 건수`} />
      ) : (
        <div className="empty-state" style={{ height: HEIGHT }}>
          아직 부적합 판정된 건이 없습니다
        </div>
      )}
    </Card>
  )
}
