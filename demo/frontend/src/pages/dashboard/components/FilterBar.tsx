import { lastFirstSelectionAt, PHASE_LABEL, type Phase } from '../data/lifecycle'
import { REGIONS } from '../data/regions'
import type { RegionName, Schedule } from '../data/types'
import { addDays, DAY_MS, endOfDay, formatDate, formatFullDate, startOfDay } from '../lib/dates'

interface FilterBarProps {
  schedule: Schedule
  asOf: number
  phase: Phase
  onAsOfChange: (asOf: number) => void
  region: RegionName | null
  onRegionChange: (region: RegionName | null) => void
  playing: boolean
  onTogglePlay: () => void
}

export function FilterBar({
  schedule,
  asOf,
  phase,
  onAsOfChange,
  region,
  onRegionChange,
  playing,
  onTogglePlay,
}: FilterBarProps) {
  const firstDay = startOfDay(schedule.openAt)
  const totalDays = Math.round((startOfDay(schedule.announcementAt) - firstDay) / DAY_MS)
  const dayIndex = Math.round((startOfDay(asOf) - firstDay) / DAY_MS)
  const milestones = [
    { label: '접수 시작', at: schedule.openAt },
    { label: '접수 마감', at: schedule.closeAt },
    { label: '시군 1차 선정 완료', at: lastFirstSelectionAt(schedule) },
    { label: '2차 검증 완료', at: schedule.secondVerificationAt },
    { label: '결과 발표', at: schedule.announcementAt },
  ]

  return (
    <section className="filterbar" aria-label="대시보드 필터">
      <div className="filter-asof">
        <div className="filter-asof-head">
          <span className="filter-label">기준일</span>
          <strong className="asof-date">{formatFullDate(asOf)}</strong>
          <span className="phase-badge">{PHASE_LABEL[phase]}</span>
        </div>
        <div className="slider-row">
          <button type="button" className="play-button" onClick={onTogglePlay} aria-pressed={playing}>
            {playing ? '❚❚ 일시정지' : '▶ 재생'}
          </button>
          <input
            className="asof-slider"
            type="range"
            min={0}
            max={totalDays}
            step={1}
            value={dayIndex}
            aria-label="기준일 선택"
            onChange={(event) => onAsOfChange(endOfDay(addDays(firstDay, Number(event.target.value))))}
          />
        </div>
        <div className="milestones">
          {milestones.map((milestone) => (
            <button
              type="button"
              key={milestone.label}
              className={asOf >= milestone.at ? 'milestone is-done' : 'milestone'}
              onClick={() => onAsOfChange(endOfDay(milestone.at))}
            >
              <span className="milestone-date">{formatDate(milestone.at)}</span>
              {milestone.label}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-region">
        <label className="filter-label" htmlFor="region-filter">
          시군
        </label>
        <select
          id="region-filter"
          value={region ?? ''}
          onChange={(event) => onRegionChange(event.target.value === '' ? null : (event.target.value as RegionName))}
        >
          <option value="">전북 전체 (14개 시군)</option>
          {REGIONS.map((profile) => (
            <option key={profile.name} value={profile.name}>
              {profile.name}
            </option>
          ))}
        </select>
        <p className="filter-hint">지도·심사 진행 차트·상세 표에서 시군을 클릭해도 선택됩니다.</p>
      </div>
    </section>
  )
}
