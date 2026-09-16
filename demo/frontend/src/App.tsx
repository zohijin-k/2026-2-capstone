/**
 * 데모 진입점. 신청자 화면과 담당자 화면을 한 번에 시연한다.
 *
 * 두 화면을 동시에 마운트해 두고 보이기만 전환한다. 전환할 때마다 언마운트하면
 * 작성하던 내용이 날아가는데, 시연 중 두 화면을 오가는 것이 기본 동선이라
 * 상태를 유지하는 편이 맞다.
 *
 * 다만 `신청자` 탭은 "처음으로" 버튼을 겸한다. 시연을 한 바퀴 돌린 뒤 다시
 * 처음부터 보여줘야 하는데, 그때 눌러야 할 곳이 화면마다 다르면 안 된다.
 * 누르면 신청자 화면을 새로 마운트해 사업 선택 화면부터 다시 시작한다.
 * (담당자 탭으로 넘어갔다 돌아올 때도 마찬가지로 초기화된다.)
 */

import { useState } from 'react'

import ApplyFlow from './pages/applicant/ApplyFlow.tsx'
import OfficerConsole from './pages/officer/OfficerConsole.tsx'
import './app-shell.css'

type Mode = 'applicant' | 'officer'

const MODES: { key: Mode; label: string }[] = [
  { key: 'applicant', label: '신청자' },
  { key: 'officer', label: '담당자' },
]

export default function App() {
  const [mode, setMode] = useState<Mode>('applicant')
  /** 값이 바뀌면 신청자 화면이 새로 마운트돼 사업 선택 화면으로 돌아간다. */
  const [applicantKey, setApplicantKey] = useState(0)

  const pick = (next: Mode) => {
    if (next === 'applicant') setApplicantKey((k) => k + 1)
    setMode(next)
    window.scrollTo({ top: 0 })
  }

  return (
    <>
      <nav className="shell" aria-label="화면 전환">
        <span className="shell__title">
          전북청년 두배적금·취업지원패키지 신청서류 자동 검토 시스템 <em>(데모)</em>
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

      <div style={{ display: mode === 'applicant' ? 'block' : 'none' }}>
        <ApplyFlow key={applicantKey} />
      </div>
      <div style={{ display: mode === 'officer' ? 'block' : 'none' }}>
        <OfficerConsole />
      </div>
    </>
  )
}
