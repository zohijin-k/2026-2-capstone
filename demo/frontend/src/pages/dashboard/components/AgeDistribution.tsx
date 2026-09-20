import { useMemo } from 'react'
import { baseOption, categoryAxis, HOVER_SHADOW, tooltipRow, tooltipTitle, valueAxis } from '../charts/base'
import { AGE_BANDS } from '../data/scoring'
import { fmtInt, fmtPct } from '../lib/format'
import type { AgePoint } from '../lib/metrics'
import type { ChartTokens } from '../theme'
import { Card } from './Card'
import { Chart } from './Chart'

interface AgeDistributionProps {
  ages: AgePoint[]
  averageAge: number | null
  applicants: number
  scopeLabel: string
  tokens: ChartTokens
  className?: string
}

export function AgeDistribution({ ages, averageAge, applicants, scopeLabel, tokens, className }: AgeDistributionProps) {
  const bandCounts = AGE_BANDS.map((_, band) =>
    ages.filter((point) => point.band === band).reduce((sum, point) => sum + point.count, 0),
  )

  const option = useMemo(() => {
    const base = baseOption(tokens)
    return {
      ...base,
      // 범례는 위쪽 stat-strip(색상 칩 + 비율)이 대신한다
      grid: { left: 4, right: 28, top: 16, bottom: 0, containLabel: true },
      tooltip: {
        ...base.tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: HOVER_SHADOW } },
        formatter: (params: unknown) => {
          const index = (params as { dataIndex: number }[])[0]?.dataIndex ?? -1
          const point = ages[index]
          if (!point) return ''
          return (
            tooltipTitle(`만 ${point.age}세`) +
            tooltipRow(
              tokens.ordinal[point.band],
              AGE_BANDS[point.band].label,
              `${fmtInt(point.count)}명 · ${applicants ? fmtPct(point.count / applicants, 1) : '—'}`,
            )
          )
        },
      },
      xAxis: categoryAxis(
        tokens,
        ages.map((point) => String(point.age)),
        { name: '세', nameLocation: 'end', nameGap: 6, nameTextStyle: { color: tokens.muted, fontSize: 11 } },
      ),
      yAxis: valueAxis(tokens),
      series: AGE_BANDS.map((band, bandIndex) => ({
        name: band.label,
        type: 'bar',
        stack: 'age',
        barCategoryGap: '18%',
        itemStyle: { color: tokens.ordinal[bandIndex], borderRadius: [3, 3, 0, 0] },
        data: ages.map((point) => (point.band === bandIndex ? point.count : null)),
      })),
    }
  }, [ages, applicants, tokens])

  return (
    <Card className={className} title="연령 분포" subtitle={`${scopeLabel} · '25.12.31. 기준 만 나이 · 제출 완료 건`}>
      <div className="stat-strip">
        <div className="stat">
          <span className="stat-label">평균 연령</span>
          <strong className="stat-value">{averageAge === null ? '—' : `${averageAge.toFixed(1)}세`}</strong>
        </div>
        {AGE_BANDS.map((band, index) => (
          <div className="stat" key={band.label}>
            <span className="stat-label">
              <i className="swatch" style={{ background: tokens.ordinal[index] }} />
              {band.label}
            </span>
            <strong className="stat-value stat-value-sm">
              {applicants ? fmtPct(bandCounts[index] / applicants, 0) : '—'}
            </strong>
          </div>
        ))}
      </div>
      <Chart option={option} height={290} ariaLabel={`${scopeLabel} 연령별 신청자 수`} />
    </Card>
  )
}
