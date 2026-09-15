/**
 * 데모 진입점. 신청자 화면과 담당자 화면을 한 번에 시연한다.
 *
 * 두 화면을 동시에 마운트해 두고 보이기만 전환한다. 신청자 화면은 처음 뜰 때
 * 임시저장용 신청 건을 하나 만드는데, 전환할 때마다 언마운트하면 빈 신청 건이
 * 계속 쌓이고 작성하던 내용도 날아간다. 시연 중 화면을 오가는 것이 기본 동선이라
 * 상태를 유지하는 편이 맞다.
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
              onClick={() => setMode(m.key)}
            >
              {m.label}
            </button>
          ))}
        </span>
      </nav>

      <div style={{ display: mode === 'applicant' ? 'block' : 'none' }}>
        <ApplyFlow />
      </div>
      <div style={{ display: mode === 'officer' ? 'block' : 'none' }}>
        <OfficerConsole />
      </div>
    </>
  )
}
