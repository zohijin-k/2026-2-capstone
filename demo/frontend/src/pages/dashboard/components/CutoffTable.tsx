import type { RegionName } from '../data/types'
import { fmtInt } from '../lib/format'
import type { CutoffEstimate, RegionRow } from '../lib/metrics'
import { Card } from './Card'

const KIND_LABEL: Record<CutoffEstimate['kind'], string | null> = {
  confirmed: '확정',
  estimated: '예상',
  undersubscribed: '정원 미달',
  none: null,
}

interface CutoffTableProps {
  rows: RegionRow[]
  selected: RegionName | null
  onSelect: (region: RegionName | null) => void
  className?: string
}

/** 담당자용 — 시군별 선정 커트라인 (고득점순으로 정원을 채우는 최저 총점) */
export function CutoffTable({ rows, selected, onSelect, className }: CutoffTableProps) {
  // 표가 항상 전체 시군을 보여주므로 요약값도 시군 필터와 무관하게 전체 기준
  const scores = rows
    .map((row) => row.cutoff.score)
    .filter((score): score is number => score !== null)
    .sort((a, b) => a - b)
  const summary = scores.length
    ? { min: scores[0], max: scores[scores.length - 1], median: scores[Math.floor((scores.length - 1) / 2)] }
    : null

  return (
    <Card
      className={className}
      title="시군별 선정 커트라인"
      subtitle="전체 시군 · 2차 검증 전에는 판정 적합률을 미판정 건에 적용한 예상값"
    >
      <div className="stat-strip">
        <div className="stat">
          <span className="stat-label">중앙값</span>
          <strong className="stat-value">{summary ? `${summary.median}점` : '—'}</strong>
        </div>
        <div className="stat">
          <span className="stat-label">최저</span>
          <strong className="stat-value stat-value-sm">{summary ? `${summary.min}점` : '—'}</strong>
        </div>
        <div className="stat">
          <span className="stat-label">최고</span>
          <strong className="stat-value stat-value-sm">{summary ? `${summary.max}점` : '—'}</strong>
        </div>
      </div>
      <div className="table-wrap">
        <table className="region-table region-table-compact">
          <thead>
            <tr>
              <th scope="col">시군</th>
              <th scope="col">정원</th>
              <th scope="col">적합 판정</th>
              <th scope="col">커트라인</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = row.name === selected
              const kind = KIND_LABEL[row.cutoff.kind]
              return (
                <tr
                  key={row.name}
                  className={isSelected ? 'is-selected' : undefined}
                  onClick={() => onSelect(isSelected ? null : row.name)}
                >
                  <th scope="row">
                    <button type="button" className="row-button" aria-pressed={isSelected}>
                      {row.name}
                    </button>
                  </th>
                  <td>{fmtInt(row.quota)}</td>
                  <td>{fmtInt(row.eligible)}</td>
                  <td>
                    {row.cutoff.score === null ? '—' : `${row.cutoff.score}점`}
                    {kind && <span className={`tag tag-${row.cutoff.kind}`}>{kind}</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
