import { useEffect, useState } from 'react'

import { fetchPrograms, type Program } from './api.ts'

/**
 * P0 스캐폴딩 화면.
 *
 * 백엔드의 사업 설정이 실제로 내려오는지 확인하는 용도다. P1에서 랜딩 →
 * 자가진단 → 신청서로 대체된다.
 */
export default function App() {
  const [programs, setPrograms] = useState<Program[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchPrograms()
      .then(setPrograms)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: '32px 16px' }}>
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>
        전북청년 두배적금 · 취업지원패키지
      </h1>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        신청서류 자동 검토 및 자격 심사 시스템 — 데모
      </p>

      {error && <p style={{ color: '#c00' }}>{error}</p>}
      {!error && programs.length === 0 && <p>불러오는 중…</p>}

      {programs.map((p) => (
        <section
          key={p.code}
          style={{
            border: '1px solid var(--form-border)',
            padding: 16,
            marginTop: 16,
          }}
        >
          <h2 style={{ fontSize: 16, margin: '0 0 8px' }}>{p.name}</h2>
          <dl style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: 4, margin: 0 }}>
            <dt>신청기간</dt>
            <dd style={{ margin: 0 }}>
              {p.apply_period[0]} ~ {p.apply_period[1]}
            </dd>
            <dt>선발 방식</dt>
            <dd style={{ margin: 0 }}>
              {p.selection === 'scored' ? '심사표 100점 점수제' : '선착순'}
            </dd>
            <dt>서류 보완</dt>
            <dd style={{ margin: 0 }}>
              {p.allows_supplement ? `${p.supplement_days}일 내 보완 가능` : '보완 불가'}
            </dd>
            <dt>서류 인정일</dt>
            <dd style={{ margin: 0 }}>{p.document_cutoff} 이후 발급분</dd>
            <dt>소득 요건</dt>
            <dd style={{ margin: 0 }}>
              {p.has_income_requirement ? '중위소득 140% 이하' : '없음'}
            </dd>
            {p.quota_total !== null && (
              <>
                <dt>선정 인원</dt>
                <dd style={{ margin: 0 }}>{p.quota_total.toLocaleString()}명</dd>
              </>
            )}
          </dl>
        </section>
      ))}
    </main>
  )
}
