/**
 * 데모 진입점. 신청자 · 담당자 · 현황 세 화면을 한 번에 시연한다.
 *
 * 신청자와 담당자는 동시에 마운트해 두고 보이기만 전환한다. 전환할 때마다
 * 언마운트하면 작성하던 내용이 날아가는데, 시연 중 두 화면을 오가는 것이 기본
 * 동선이라 상태를 유지하는 편이 맞다.
 *
 * 다만 `신청자` 탭은 "처음으로" 버튼을 겸한다. 시연을 한 바퀴 돌린 뒤 다시
 * 처음부터 보여줘야 하는데, 그때 눌러야 할 곳이 화면마다 다르면 안 된다.
 * 누르면 신청자 화면을 새로 마운트해 사업 선택 화면부터 다시 시작한다.
 * (담당자 탭으로 넘어갔다 돌아올 때도 마찬가지로 초기화된다.)
 *
 * 현황 화면만 다르게 다룬다. 처음 열 때까지는 마운트하지 않고, 한 번 연 뒤로는
 * 나머지와 같이 숨김 전환한다. 이유는 둘이다.
 *
 *   - 목업 12,821건을 모듈 로드 시점에 만든다. 항상 마운트하면 신청자 첫 화면이
 *     그만큼 늦게 그려진다.
 *   - 기준일 재생 타이머가 200ms마다 전건을 다시 집계한다. 보이지 않을 때도
 *     돌면 시연 내내 CPU를 태우므로 `active`를 내려보내 멈추게 한다.
 *
 * 화면 토큰은 `body[data-view]`로 갈린다. 세 화면이 같은 이름의 CSS 변수를 다른
 * 값으로 쓰기 때문이다 — `styles/tokens-form.css` 머리말 참고.
 */

import { Suspense, lazy, useEffect, useState } from 'react'

import { INITIAL, type TabKey, syncViewParam } from './app/initial-params.ts'
import ApplyFlow from './pages/applicant/ApplyFlow.tsx'
import OfficerConsole from './pages/officer/OfficerConsole.tsx'
import './app-shell.css'

//: echarts·전북 경계·목업 생성기가 통째로 이 청크로 빠진다. 신청자만 보고 갈
//: 사람에게 760KB를 먼저 내려보내지 않기 위한 것이다.
const DashboardPage = lazy(() => import('./pages/dashboard/DashboardPage.tsx'))

const MODES: { key: TabKey; label: string }[] = [
  { key: 'apply', label: '신청자' },
  { key: 'officer', label: '담당자' },
  { key: 'status', label: '현황' },
]

export default function App() {
  const [mode, setMode] = useState<TabKey>(INITIAL.view)
  /** 값이 바뀌면 신청자 화면이 새로 마운트돼 사업 선택 화면으로 돌아간다. */
  const [applicantKey, setApplicantKey] = useState(0)
  /** 현황 화면은 한 번이라도 연 뒤부터 계속 마운트해 둔다. */
  const [statusMounted, setStatusMounted] = useState(INITIAL.view === 'status')

  useEffect(() => {
    document.body.dataset.view = mode
  }, [mode])

  const pick = (next: TabKey) => {
    if (next === 'apply') setApplicantKey((k) => k + 1)
    if (next === 'status') setStatusMounted(true)
    setMode(next)
    syncViewParam(next)
    window.scrollTo({ top: 0 })
  }

  return (
    <>
      <nav className="shell" aria-label="화면 전환">
        <span className="shell__title">
          전북청년 두배적금·취업지원패키지 신청서류 자동 검토 시스템
        </span>
        <span className="shell__tabs">
          {MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              className={m.key === mode ? 'shell__tab shell__tab--on' : 'shell__tab'}
              onClick={() => pick(m.key)}
            >
              {m.label}
            </button>
          ))}
        </span>
      </nav>

      <div style={{ display: mode === 'apply' ? 'block' : 'none' }}>
        <ApplyFlow key={applicantKey} />
      </div>
      <div style={{ display: mode === 'officer' ? 'block' : 'none' }}>
        <OfficerConsole />
      </div>
      {statusMounted && (
        <div style={{ display: mode === 'status' ? 'block' : 'none' }}>
          <Suspense fallback={<p className="shell__loading">현황 화면을 불러오는 중…</p>}>
            <DashboardPage active={mode === 'status'} />
          </Suspense>
        </div>
      )}
    </>
  )
}
