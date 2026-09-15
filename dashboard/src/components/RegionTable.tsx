import type { RegionName } from '../data/types'
import { fmtDays, fmtInt, fmtPct, fmtRatio } from '../lib/format'
import type { RegionRow } from '../lib/metrics'
import { Card } from './Card'

function ProgressCell({ value }: { value: number }) {
  return (
    <span className="inline-meter">
      <span className="inline-meter-track" aria-hidden="true">
        <span className="inline-meter-fill" style={{ width: `${Math.min(100, value * 100)}%` }} />
      </span>
      {fmtPct(value, 0)}
    </span>
  )
}

function selectionText(finalSelected: number, firstSelected: number) {
  if (finalSelected > 0) return <>{fmtInt(finalSelected)}명<span className="tag tag-confirmed">최종</span></>
  if (firstSelected > 0) return <>{fmtInt(firstSelected)}명<span className="tag">1차</span></>
  return '—'
}

interface RegionTableProps {
  rows: RegionRow[]
  selected: RegionName | null
  onSelect: (region: RegionName | null) => void
  className?: string
}

export function RegionTable({ rows, selected, onSelect, className }: RegionTableProps) {
  const totals = rows.reduce(
    (acc, row) => {
      const decided = row.eligible + row.rejected
      acc.quota += row.quota
      acc.submitted += row.submitted
      acc.decided += decided
      acc.eligible += row.eligible
      acc.processingDays += (row.avgProcessingDays ?? 0) * decided
      acc.firstSelected += row.firstSelected
      acc.finalSelected += row.finalSelected
      return acc
    },
    { quota: 0, submitted: 0, decided: 0, eligible: 0, processingDays: 0, firstSelected: 0, finalSelected: 0 },
  )

  return (
    <Card className={className} title="시군별 상세" subtitle="행을 선택하면 시군 필터가 적용됩니다">
      <div className="table-wrap">
        <table className="region-table">
          <thead>
            <tr>
              <th scope="col">시군</th>
              <th scope="col">정원</th>
              <th scope="col">접수</th>
              <th scope="col">경쟁률</th>
              <th scope="col">심사 진행률</th>
              <th scope="col">적합률</th>
              <th scope="col">평균 처리기간</th>
              <th scope="col">선정</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = row.name === selected
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
                  <td>{fmtInt(row.submitted)}</td>
                  <td>{row.submitted ? fmtRatio(row.competition) : '—'}</td>
                  <td>
                    <ProgressCell value={row.progress} />
                  </td>
                  <td>{row.eligibleRate === null ? '—' : fmtPct(row.eligibleRate)}</td>
                  <td>{row.avgProcessingDays === null ? '—' : fmtDays(row.avgProcessingDays)}</td>
                  <td>{selectionText(row.finalSelected, row.firstSelected)}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">합계</th>
              <td>{fmtInt(totals.quota)}</td>
              <td>{fmtInt(totals.submitted)}</td>
              <td>{totals.submitted ? fmtRatio(totals.submitted / totals.quota) : '—'}</td>
              <td>
                <ProgressCell value={totals.submitted ? totals.decided / totals.submitted : 0} />
              </td>
              <td>{totals.decided ? fmtPct(totals.eligible / totals.decided) : '—'}</td>
              <td>{totals.decided ? fmtDays(totals.processingDays / totals.decided) : '—'}</td>
              <td>{selectionText(totals.finalSelected, totals.firstSelected)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}
