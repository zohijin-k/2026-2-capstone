/**
 * 담당자 콘솔 — 접수 목록 ↔ 건별 분할 심사 (P4).
 *
 * 상단의 **역할 전환 토글**이 이 화면의 축이다 (R4.5). 시행지침의 선발 절차가
 * 읍·면·동 → 시군 → 도·청년허브센터로 올라가는데, 같은 화면에서 보이는 범위와
 * 가능한 액션만 달라지는 것을 보여주면 충분하다. 데모는 로그인을 하지 않는다 —
 * 인증이 아니라 절차 구조를 시연하는 것이 목적이다.
 */

import { useCallback, useEffect, useState } from 'react'

import {
  fetchOfficerList,
  fetchOfficerRoles,
  postBulkDecision,
  type DecisionKey,
  type OfficerList,
  type OfficerListQuery,
  type OfficerRole,
} from '../../api.ts'
import ApplicationList from './ApplicationList.tsx'
import ReviewDetail from './ReviewDetail.tsx'
import './officer.css'

const DEFAULT_QUERY: OfficerListQuery = { role: 'province', page: 1, page_size: 20 }

export default function OfficerConsole() {
  const [roles, setRoles] = useState<OfficerRole[]>([])
  const [query, setQuery] = useState<OfficerListQuery>(DEFAULT_QUERY)
  const [list, setList] = useState<OfficerList | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchOfficerRoles()
      .then(setRoles)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const reload = useCallback(() => {
    fetchOfficerList(query)
      .then((body) => {
        setList(body)
        setError('')
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [query])

  useEffect(reload, [reload])

  const patch = (next: Partial<OfficerListQuery>) => {
    setQuery((prev) => ({ ...prev, ...next }))
    setSelected([])
  }

  /** 역할을 바꾸면 관할 선택은 백엔드가 다시 정해준다 — 여기서는 비워 보낸다. */
  const switchRole = (role: string) => {
    setOpenId(null)
    setQuery({ ...DEFAULT_QUERY, role })
    setSelected([])
  }

  const bulk = (decision: DecisionKey) => {
    if (!list || selected.length === 0) return
    setBusy(true)
    postBulkDecision({
      role: list.role.key,
      decision,
      memo: `${list.role.name} 일괄 처리`,
      application_ids: selected,
    })
      .then(() => {
        setSelected([])
        reload()
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const activeRole = list?.role ?? roles.find((r) => r.key === query.role) ?? null

  return (
    <div className="officer">
      <header className="officer__head">
        <h1>담당자 심사</h1>
        <div className="officer__roles" role="group" aria-label="역할 전환">
          {roles.map((r) => (
            <button
              key={r.key}
              type="button"
              className={r.key === query.role ? 'officer__role officer__role--on' : 'officer__role'}
              onClick={() => switchRole(r.key)}
            >
              {r.name}
            </button>
          ))}
        </div>
        {activeRole && (
          <p className="officer__scope">
            <strong>{activeRole.stage}</strong> · 보이는 범위: {activeRole.scope}
            {activeRole.quota_ratio !== null && (
              <> · 선발 {Math.round(activeRole.quota_ratio * 100)}%</>
            )}
          </p>
        )}
        {activeRole && (
          <ul className="officer__notes">
            {activeRole.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}
      </header>

      {error && <p className="officer__error">{error}</p>}

      {openId !== null ? (
        <ReviewDetail
          applicationId={openId}
          role={query.role}
          onBack={() => setOpenId(null)}
          onDecided={reload}
        />
      ) : list ? (
        <ApplicationList
          list={list}
          query={query}
          onQuery={patch}
          onOpen={setOpenId}
          selected={selected}
          onSelect={setSelected}
          onBulk={bulk}
          busy={busy}
        />
      ) : (
        <p className="officer__loading">접수 목록을 불러오는 중…</p>
      )}
    </div>
  )
}
