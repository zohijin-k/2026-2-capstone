import type { RegionName } from '../data/types'
import { fmtDays, fmtInt, fmtPct, fmtRatio } from '../lib/format'
import type { Snapshot } from '../lib/metrics'

interface Tile {
  label: string
  value: string
  unit?: string
  caption: string
  meter?: number
}

function competitionTile({ totals, regions }: Snapshot, region: RegionName | null): Tile {
  if (!totals.submitted) return { label: '경쟁률', value: '—', caption: '접수 건 없음' }
  if (region) {
    const allSubmitted = regions.reduce((sum, row) => sum + row.submitted, 0)
    const allQuota = regions.reduce((sum, row) => sum + row.quota, 0)
    return { label: '경쟁률', value: fmtRatio(totals.competition), caption: `전북 전체 ${fmtRatio(allSubmitted / allQuota)}` }
  }
  const top = regions.reduce((best, row) => (row.competition > best.competition ? row : best))
  return { label: '경쟁률', value: fmtRatio(totals.competition), caption: `최고 ${top.name} ${fmtRatio(top.competition)}` }
}

function selectionTile({ totals }: Snapshot): Tile {
  if (totals.finalSelected > 0) {
    return {
      label: '선정자',
      value: fmtInt(totals.finalSelected),
      unit: '명',
      caption: `최종 선정 · 정원 ${fmtInt(totals.quota)}명`,
      meter: totals.finalSelected / totals.quota,
    }
  }
  if (totals.firstSelected > 0) {
    return {
      label: '선정자 (1차)',
      value: fmtInt(totals.firstSelected),
      unit: '명',
      caption: '시군 1차 선정(정원의 120%) · 2차 검증 전',
    }
  }
  return { label: '선정자', value: '—', caption: '시군 심사 완료 후 집계' }
}

function buildTiles(snapshot: Snapshot, region: RegionName | null): Tile[] {
  const { totals } = snapshot
  return [
    {
      label: '접수 건수',
      value: fmtInt(totals.submitted),
      unit: '건',
      caption: `정원 ${fmtInt(totals.quota)}명 대비 접수율 ${fmtPct(totals.submitted / totals.quota, 0)}`,
    },
    competitionTile(snapshot, region),
    {
      label: '심사 진행률',
      value: totals.progress === null ? '—' : fmtPct(totals.progress),
      caption: `판정 완료 ${fmtInt(totals.decided)} / 접수 ${fmtInt(totals.submitted)}`,
      meter: totals.progress ?? 0,
    },
    {
      label: '적합률',
      value: totals.eligibleRate === null ? '—' : fmtPct(totals.eligibleRate),
      caption: `적합 ${fmtInt(totals.eligible)} · 부적합 ${fmtInt(totals.rejected)}`,
    },
    selectionTile(snapshot),
    {
      label: '평균 처리기간',
      value: totals.avgProcessingDays === null ? '—' : totals.avgProcessingDays.toFixed(1),
      unit: totals.avgProcessingDays === null ? undefined : '일',
      caption: totals.avgProcessingDays === null ? '판정 완료 건 없음' : `접수 → 판정 완료 · ${fmtDays(totals.avgProcessingDays)}`,
    },
  ]
}

export function KpiTiles({ snapshot, region }: { snapshot: Snapshot; region: RegionName | null }) {
  return (
    <div className="kpi-grid">
      {buildTiles(snapshot, region).map((tile) => (
        <div className="kpi" key={tile.label}>
          <div className="kpi-label">{tile.label}</div>
          <div className="kpi-value">
            {tile.value}
            {tile.unit && <span className="kpi-unit">{tile.unit}</span>}
          </div>
          {tile.meter !== undefined && (
            <div className="meter" aria-hidden="true">
              <span style={{ width: `${Math.min(100, tile.meter * 100)}%` }} />
            </div>
          )}
          <div className="kpi-caption">{tile.caption}</div>
        </div>
      ))}
    </div>
  )
}
