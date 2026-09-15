import { useMemo } from 'react'
import { baseOption, categoryAxis, HOVER_SHADOW, legendOption, tooltipRow, tooltipTitle, valueAxis } from '../charts/base'
import { fmtInt } from '../lib/format'
import type { CutoffEstimate, ScoreBin } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'

interface ScoreDistributionProps {
  bins: ScoreBin[]
  /** 시군을 선택했을 때의 커트라인. 전체 보기에서는 null */
  cutoff: CutoffEstimate | null
  scopeLabel: string
  tokens: ChartTokens
  className?: string
}

export function ScoreDistribution({ bins, cutoff, scopeLabel, tokens, className }: ScoreDistributionProps) {
  const cutoffScore = cutoff?.score ?? null
  const cutoffLabel = cutoff?.kind === 'confirmed' ? '확정 커트라인' : '예상 커트라인'

  const option = useMemo(() => {
    const base = baseOption(tokens)
    const series = [
      {
        key: 'withinCutoff' as const,
        label: cutoff ? '선정권 (커트라인 이상)' : '선정권 (시군별 커트라인 이상)',
        color: tokens.series1,
      },
      { key: 'outsideCutoff' as const, label: '선정권 밖', color: tokens.neutral },
      { key: 'rejected' as const, label: '부적합 판정', color: tokens.series2 },
    ]

    return {
      ...base,
      legend: legendOption(tokens),
      grid: { left: 4, right: 40, top: 58, bottom: 0, containLabel: true },
      tooltip: {
        ...base.tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: HOVER_SHADOW } },
        formatter: (params: unknown) => {
          const index = (params as { dataIndex: number }[])[0]?.dataIndex ?? -1
          const bin = bins[index]
          if (!bin) return ''
          const total = bin.withinCutoff + bin.outsideCutoff + bin.rejected
          return (
            tooltipTitle(`총점 ${bin.score}점 · ${fmtInt(total)}명`) +
            series.map((item) => tooltipRow(item.color, item.label, `${fmtInt(bin[item.key])}명`)).join('')
          )
        },
      },
      xAxis: categoryAxis(
        tokens,
        bins.map((bin) => String(bin.score)),
        { name: '총점', nameLocation: 'end', nameGap: 8, nameTextStyle: { color: tokens.muted, fontSize: 11 } },
      ),
      yAxis: valueAxis(tokens),
      series: series.map((item, index) => ({
        name: item.label,
        type: 'bar',
        stack: 'score',
        barCategoryGap: '18%',
        itemStyle: { color: item.color, borderColor: tokens.surface, borderWidth: 1 },
        data: bins.map((bin) => bin[item.key]),
        ...(index === 0 && cutoffScore !== null
          ? {
              markLine: {
                silent: true,
                symbol: 'none',
                data: [{ xAxis: String(cutoffScore) }],
                lineStyle: { color: tokens.textPrimary, width: 1.5, type: 'solid' },
                label: {
                  formatter: `${cutoffLabel} ${cutoffScore}점`,
                  color: tokens.textPrimary,
                  fontSize: 12,
                  fontWeight: 'bold',
                  position: 'end',
                  distance: 4,
                },
              },
            }
          : {}),
      })),
    }
  }, [bins, cutoff, cutoffScore, cutoffLabel, tokens])

  return (
    <Card
      className={className}
      title="배점별 신청자 분포"
      subtitle={`${scopeLabel} · 신청서 기재값 기준 심사표 총점(소득 40·거주 25·근로 25·연령 10)`}
    >
      <Chart
        key={`${scopeLabel}-${cutoffScore ?? 'none'}`}
        option={option}
        height={340}
        ariaLabel={`${scopeLabel} 심사표 총점별 신청자 수`}
      />
    </Card>
  )
}
