import { useEffect, useMemo, useState } from 'react'
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
import { generateDataset } from './data/generate'
import { REGION_BY_NAME, TOTAL_QUOTA } from './data/regions'
import { REGION_NAMES, type RegionName } from './data/types'
import { addDays, at, endOfDay } from './lib/dates'
import { fmtInt } from './lib/format'
import { computeSnapshot } from './lib/metrics'
import { TOKENS, type ThemeMode } from './theme'

const dataset = generateDataset()
const FIRST_DAY_END = endOfDay(dataset.schedule.openAt)
const LAST_DAY_END = endOfDay(dataset.schedule.announcementAt)
/** 첫 화면: 시군 심사가 한창인 시점 */
const DEFAULT_AS_OF = endOfDay(at(2026, 4, 17))
const PLAY_INTERVAL_MS = 200

/** 링크로 특정 화면을 열 수 있도록 초기값을 쿼리에서 읽는다: ?date=2026-05-15&region=전주시&theme=dark */
const searchParams = new URLSearchParams(window.location.search)

function initialTheme(): ThemeMode {
  const requested = searchParams.get('theme')
  if (requested === 'light' || requested === 'dark') return requested
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function initialAsOf(): number {
  const match = searchParams.get('date')?.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return DEFAULT_AS_OF
  const requested = endOfDay(at(Number(match[1]), Number(match[2]), Number(match[3])))
  return Math.min(LAST_DAY_END, Math.max(FIRST_DAY_END, requested))
}

function initialRegion(): RegionName | null {
  const requested = searchParams.get('region')
  return REGION_NAMES.find((name) => name === requested) ?? null
}

export default function App() {
  const [theme, setTheme] = useState<ThemeMode>(initialTheme)
  const [asOf, setAsOf] = useState(initialAsOf)
  const [region, setRegion] = useState<RegionName | null>(initialRegion)
  const [playing, setPlaying] = useState(false)

  const tokens = TOKENS[theme]
  const snapshot = useMemo(() => computeSnapshot(dataset, asOf, region), [asOf, region])
  const scopeLabel = region ?? '전북 전체'
  /** 발표일에 도달하면 자동으로 멈춘 것으로 본다 */
  const isPlaying = playing && asOf < LAST_DAY_END

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    if (!isPlaying) return
    const timer = window.setInterval(() => {
      setAsOf((previous) => Math.min(LAST_DAY_END, endOfDay(addDays(previous, 1))))
    }, PLAY_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [isPlaying])

  const togglePlay = () => {
    if (isPlaying) {
      setPlaying(false)
      return
    }
    if (asOf >= LAST_DAY_END) setAsOf(FIRST_DAY_END)
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
            <span>전북특별자치도 · 14개 시군 · 정원 {fmtInt(TOTAL_QUOTA)}명</span>
            <span className="badge badge-mock">목업 데이터</span>
          </div>
        </div>
        <button
          type="button"
          className="ghost-button"
          onClick={() => setTheme((mode) => (mode === 'light' ? 'dark' : 'light'))}
        >
          {theme === 'light' ? '다크 모드' : '라이트 모드'}
        </button>
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
          quota={region ? REGION_BY_NAME[region].quota : TOTAL_QUOTA}
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

        {/* 배점·커트라인은 담당자만 조회 — 실서비스에서는 권한 확인 후 이 영역의 데이터를 내려줘야 함 */}
        <div className="section-divider span-12" role="separator" aria-label="담당자용 영역">
          <span className="section-divider-label">담당자용</span>
          <span className="section-divider-note">배점·커트라인 정보 · 담당자 권한으로만 조회</span>
        </div>

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
      </main>

      <footer className="footnote">
        ※ 화면의 모든 수치는 목업 데이터입니다. 시군별 접수 규모·정원·신청 일정·심사표 배점은 '26년 공고문과 시행지침을
        따르고, 연령·성별·근로유형·부적합 사유 비율과 시군별 처리 속도는 가정값입니다. 지도 경계: 통계청(2013) 시군구
        경계 기반.
      </footer>
    </div>
  )
}
