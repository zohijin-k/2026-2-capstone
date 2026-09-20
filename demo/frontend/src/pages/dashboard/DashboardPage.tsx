import { useEffect, useMemo, useState } from 'react'
import { INITIAL } from '../../app/initial-params.ts'
import { AgeDistribution } from './components/AgeDistribution'
import { CutoffTable } from './components/CutoffTable'
import { DailyTrend } from './components/DailyTrend'
import { FilterBar } from './components/FilterBar'
import { JeonbukMap } from './components/JeonbukMap'
import { KpiTiles } from './components/KpiTiles'
import { ProfileBreakdown } from './components/ProfileBreakdown'
import { RegionTable } from './components/RegionTable'
import { RejectReasons } from './components/RejectReasons'
import { ReviewStages } from './components/ReviewStages'
import { ScoreDistribution } from './components/ScoreDistribution'
import { REGION_BY_NAME, TOTAL_QUOTA } from './data/regions'
import { loadDataset, sourceReason } from './data/source'
import { REGION_NAMES, type Dataset, type RegionName } from './data/types'
import { addDays, at, endOfDay } from './lib/dates'
import { fmtInt } from './lib/format'
import { computeSnapshot } from './lib/metrics'
import { TOKENS, type ThemeMode } from './theme'
import './dashboard.css'

/** 첫 화면: 시군 심사가 한창인 시점 (목업 타임라인 기준) */
const DEFAULT_AS_OF = endOfDay(at(2026, 4, 17))
const PLAY_INTERVAL_MS = 200

/** 담당자 시점의 역할. 배점·커트라인을 받으려면 서버에 이 값을 보내야 한다. */
const STAFF_ROLE = 'province'

/**
 * 링크로 특정 화면을 열 수 있도록 초기값을 쿼리에서 읽는다:
 * `?view=status&date=2026-05-15&region=전주시&theme=dark`
 *
 * 쿼리 파싱은 `app/initial-params.ts`가 부팅 때 한 번만 해 둔다. 이 화면은 탭
 * 전환 뒤에야 지연 로드되는데, 그때 직접 `location.search`를 읽으면 셸이 이미
 * `?view=`를 갈아 끼운 뒤라 읽는 시점에 따라 값이 달라진다.
 */
function initialTheme(): ThemeMode {
  if (INITIAL.theme) return INITIAL.theme
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function initialRegion(): RegionName | null {
  return REGION_NAMES.find((name) => name === INITIAL.region) ?? null
}

/**
 * 데이터를 고르고, 고른 것으로 화면을 그린다.
 *
 * @param active 이 화면이 지금 보이는 탭인가. 숨어 있을 때 기준일 재생 타이머가
 *   계속 돌면 200ms마다 전건을 다시 집계해 시연 내내 CPU를 태운다.
 */
export default function DashboardPage({ active }: { active: boolean }) {
  const [role, setRole] = useState<string | null>(INITIAL.role)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    // 시점을 바꿀 때 이전 데이터를 지우지 않는다. 지우면 화면이 통째로 다시
    // 마운트되면서 기준일·시군 선택이 날아간다.
    loadDataset(role).then(
      (next) => {
        if (!cancelled) setDataset(next)
      },
      (reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason))
      },
    )
    return () => {
      cancelled = true
    }
  }, [role])

  if (error) {
    return (
      <div className="app">
        <p className="footnote">현황 데이터를 불러오지 못했습니다 — {error}</p>
      </div>
    )
  }
  if (!dataset) {
    return (
      <div className="app">
        <p className="footnote">현황 데이터를 불러오는 중…</p>
      </div>
    )
  }
  return (
    <DashboardView
      dataset={dataset}
      active={active}
      staffView={role !== null}
      onStaffViewChange={(on) => setRole(on ? STAFF_ROLE : null)}
    />
  )
}

interface ViewProps {
  dataset: Dataset
  active: boolean
  staffView: boolean
  onStaffViewChange: (on: boolean) => void
}

function DashboardView({ dataset, active, staffView, onStaffViewChange }: ViewProps) {
  const firstDayEnd = endOfDay(dataset.schedule.openAt)
  const lastDayEnd = endOfDay(dataset.schedule.announcementAt)

  const [theme, setTheme] = useState<ThemeMode>(initialTheme)
  const [asOf, setAsOf] = useState(() => {
    const match = INITIAL.date?.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    const requested = match
      ? endOfDay(at(Number(match[1]), Number(match[2]), Number(match[3])))
      : DEFAULT_AS_OF
    return Math.min(lastDayEnd, Math.max(firstDayEnd, requested))
  })
  const [region, setRegion] = useState<RegionName | null>(initialRegion)
  const [playing, setPlaying] = useState(false)

  const tokens = TOKENS[theme]
  const snapshot = useMemo(() => computeSnapshot(dataset, asOf, region), [dataset, asOf, region])
  const scopeLabel = region ?? '전북 전체'
  /** 발표일에 도달하거나 다른 탭으로 넘어가면 자동으로 멈춘 것으로 본다 */
  const isPlaying = playing && active && asOf < lastDayEnd

  const totalQuota = dataset.quotaByRegion
    ? Object.values(dataset.quotaByRegion).reduce((sum, value) => sum + (value ?? 0), 0)
    : TOTAL_QUOTA
  const live = dataset.source === 'live'

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    if (!isPlaying) return
    const timer = window.setInterval(() => {
      setAsOf((previous) => Math.min(lastDayEnd, endOfDay(addDays(previous, 1))))
    }, PLAY_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [isPlaying, lastDayEnd])

  const togglePlay = () => {
    if (isPlaying) {
      setPlaying(false)
      return
    }
    if (asOf >= lastDayEnd) setAsOf(firstDayEnd)
    setPlaying(true)
  }

  const changeAsOf = (value: number) => {
    setPlaying(false)
    setAsOf(value)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>전북청년 함께 두배적금 신청·심사 현황</h1>
          <div className="topbar-meta">
            <span>전북특별자치도 · 14개 시군 · 정원 {fmtInt(totalQuota)}명</span>
            {/* 무엇을 보고 있는지 숨기지 않는다. 왜 그 모드인지는 툴팁에 있다. */}
            <span
              className={live ? 'badge badge-live' : 'badge badge-mock'}
              title={sourceReason(dataset.source)}
            >
              {live ? `실데이터 · 접수 ${fmtInt(snapshot.totals.submitted)}건` : '목업 데이터'}
            </span>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="ghost-button"
            aria-pressed={staffView}
            onClick={() => onStaffViewChange(!staffView)}
          >
            {staffView ? '신청자 시점' : '담당자 시점'}
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => setTheme((mode) => (mode === 'light' ? 'dark' : 'light'))}
          >
            {theme === 'light' ? '다크 모드' : '라이트 모드'}
          </button>
        </div>
      </header>

      <FilterBar
        schedule={dataset.schedule}
        asOf={asOf}
        phase={snapshot.phase}
        onAsOfChange={changeAsOf}
        region={region}
        onRegionChange={setRegion}
        playing={isPlaying}
        onTogglePlay={togglePlay}
      />

      <main className="grid">
        <div className="span-12">
          <KpiTiles snapshot={snapshot} region={region} />
        </div>

        <JeonbukMap className="span-5" rows={snapshot.regions} selected={region} onSelect={setRegion} tokens={tokens} />
        <DailyTrend
          className="span-7"
          daily={snapshot.daily}
          quota={
            region
              ? (dataset.quotaByRegion?.[region] ?? REGION_BY_NAME[region].quota)
              : totalQuota
          }
          scopeLabel={scopeLabel}
          tokens={tokens}
        />

        <ReviewStages className="span-7" rows={snapshot.regions} selected={region} onSelect={setRegion} tokens={tokens} />
        <RejectReasons className="span-5" reasons={snapshot.rejectReasons} scopeLabel={scopeLabel} tokens={tokens} />

        <AgeDistribution
          className="span-5"
          ages={snapshot.demographics.ages}
          averageAge={snapshot.demographics.averageAge}
          applicants={snapshot.demographics.applicants}
          scopeLabel={scopeLabel}
          tokens={tokens}
        />
        <ProfileBreakdown className="span-7" demographics={snapshot.demographics} scopeLabel={scopeLabel} />

        <RegionTable className="span-12" rows={snapshot.regions} selected={region} onSelect={setRegion} />

        {/* 배점·커트라인은 담당자만 조회.
            화면에서 가리는 것만으로는 부족하다 — 집계가 전부 브라우저에서 돌기 때문에
            숨긴 값도 메모리에는 그대로 남는다. 그래서 담당자 시점이 아니면 서버가
            배점 자체를 내려주지 않고, 여기서는 그 사실을 밝히기만 한다. */}
        <div className="section-divider span-12" role="separator" aria-label="담당자용 영역">
          <span className="section-divider-label">담당자용</span>
          <span className="section-divider-note">배점·커트라인 정보 · 담당자 권한으로만 조회</span>
        </div>

        {dataset.scores === undefined ? (
          <p className="span-12 staff-only withheld">
            {dataset.scoresWithheldReason ??
              '배점·커트라인은 담당자 시점에서만 조회할 수 있습니다.'}{' '}
            <button type="button" className="ghost-button" onClick={() => onStaffViewChange(true)}>
              담당자 시점으로 보기
            </button>
          </p>
        ) : (
          <>
            <ScoreDistribution
              className="span-7 staff-only"
              bins={snapshot.scoreBins}
              cutoff={snapshot.totals.cutoff}
              scopeLabel={scopeLabel}
              tokens={tokens}
            />
            <CutoffTable
              className="span-5 staff-only"
              rows={snapshot.regions}
              selected={region}
              onSelect={setRegion}
            />
          </>
        )}
      </main>

      <footer className="footnote">
        {live ? (
          <>
            ※ 접수된 신청 건에서 집계한 값입니다. 정원·심사표 배점은 '26년 공고문과 시행지침을 따릅니다. 지도 경계:
            통계청(2013) 시군구 경계 기반.
            <br />
            ※ 엔진이 서류·자격 심사를 제출과 동시에 끝내므로 <b>심사 진행률·평균 처리기간은 실데이터로 산출되지
            않습니다.</b> 접수가 시연 당일에 몰려 일별 추이와 시군 비교도 의미가 없고, 1차·최종 선정은 판단 기록이 한
            벌뿐이라 두 단계를 동시에 볼 수 없습니다. 이 항목들은 0이 아니라 해당 없음으로 읽어야 합니다.
          </>
        ) : (
          <>
            ※ 화면의 모든 수치는 목업 데이터입니다. 시군별 접수 규모·정원·신청 일정·심사표 배점은 '26년 공고문과
            시행지침을 따르고, 연령·성별·근로유형·부적합 사유 비율과 시군별 처리 속도는 가정값입니다. 지도 경계:
            통계청(2013) 시군구 경계 기반.
          </>
        )}
        {dataset.notes?.length ? <div className="footnote-notes">※ {dataset.notes.join(' ')}</div> : null}
      </footer>
    </div>
  )
}
