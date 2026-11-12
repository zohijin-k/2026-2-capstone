/**
 * 담당자 콘솔 — 접수 목록 ↔ 건별 분할 심사 (P4).
 *
 * 상단의 **역할 전환 토글**이 이 화면의 축이다 (R4.5). 시행지침의 선발 절차가
 * 읍·면·동 → 시군 → 도·청년허브센터로 올라가는데, 같은 화면에서 보이는 범위와
 * 가능한 액션만 달라지는 것을 보여주면 충분하다. 데모는 로그인을 하지 않는다 —
 * 인증이 아니라 절차 구조를 시연하는 것이 목적이다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  fetchOfficerList,
  fetchOfficerRoles,
  isOfficerMockActive,
  postBulkDecision,
  type DecisionKey,
  type OfficerList,
  type OfficerListQuery,
  type OfficerRole,
} from '../../api.ts'
import ApplicationList from './ApplicationList.tsx'
import ReviewDetail from './ReviewDetail.tsx'
import CriteriaEditor from '../../components/CriteriaEditor.tsx'
import { Skeleton, SkeletonBlock, SkeletonLine } from '../../components/Skeleton.tsx'
import useDelayedFlag from '../../hooks/useDelayedFlag.ts'
import { currentMode, currentParams, routeUrl } from '../../navigation-url.ts'
import './officer.css'

const DEFAULT_QUERY: OfficerListQuery = { role: 'province', page: 1, page_size: 20 }
const QUERY_KEYS = [
  'region', 'town', 'program', 'status', 'ai_status', 'submitted_from', 'submitted_to', 'sort',
] as const

function savedOfficerPage(): {
  query: OfficerListQuery
  open: { id: number; slot: string | null } | null
  showCriteria: boolean
  criteriaProgram: string
} | null {
  const params = currentParams()
  const detailRoute = /^\/officer(?:\/([^/]+))?(?:\/review\/([1-9]\d*))?\/?$/.exec(window.location.pathname)
  const criteriaRoute = /^\/officer\/criteria\/([^/]+)\/?$/.exec(window.location.pathname)
  const legacy = [...QUERY_KEYS.map((key) => `o_${key}`), 'o_role', 'o_page', 'o_page_size', 'o_open', 'o_slot', 'o_criteria', 'o_criteria_program'].some((key) => params.has(key))
  if (!detailRoute && !criteriaRoute && !legacy) return null
  const query: OfficerListQuery = {
    ...DEFAULT_QUERY,
    role: detailRoute?.[1] || params.get('role') || params.get('o_role') || DEFAULT_QUERY.role,
  }
  for (const key of QUERY_KEYS) {
    const value = params.get(key === 'ai_status' ? 'ai' : key) ?? params.get(`o_${key}`)
    if (value) query[key] = value
  }
  const page = Number(params.get('page') ?? params.get('o_page'))
  const pageSize = Number(params.get('page_size') ?? params.get('o_page_size'))
  if (Number.isSafeInteger(page) && page > 0) query.page = page
  if (Number.isSafeInteger(pageSize) && pageSize > 0) query.page_size = pageSize
  const openId = Number(detailRoute?.[2] ?? params.get('o_open'))
  return {
    query,
    open: Number.isSafeInteger(openId) && openId > 0 ? { id: openId, slot: params.get('slot') ?? params.get('o_slot') } : null,
    showCriteria: criteriaRoute !== null || params.get('o_criteria') === '1',
    criteriaProgram: criteriaRoute?.[1] === 'job_package' || params.get('o_criteria_program') === 'job_package' ? 'job_package' : 'double_savings',
  }
}

export default function OfficerConsole() {
  const [initialPage] = useState(savedOfficerPage)
  const initialUrlWrite = useRef(true)
  const [roles, setRoles] = useState<OfficerRole[]>([])
  const [query, setQuery] = useState<OfficerListQuery>(initialPage?.query ?? DEFAULT_QUERY)
  const [list, setList] = useState<OfficerList | null>(null)
  /**
   * 열려 있는 심사 건. `slot`은 목록의 서류 칸을 눌러 들어왔을 때 띄울 서류다 —
   * 행을 눌러 들어오면 null이고 상세가 첫 서류를 연다.
   */
  const [open, setOpen] = useState<{ id: number; slot: string | null } | null>(initialPage?.open ?? null)
  const [selected, setSelected] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /** 목업으로 넘어갔는지는 목록을 한 번 읽어 봐야 안다 — 응답이 온 뒤에 다시 잰다. */
  const [mock, setMock] = useState(isOfficerMockActive())
  const [showCriteria, setShowCriteria] = useState(initialPage?.showCriteria ?? false)
  const [criteriaProgram, setCriteriaProgram] = useState(initialPage?.criteriaProgram ?? 'double_savings')
  const showListSkeleton = useDelayedFlag(!list && !error && !showCriteria && open === null)

  useEffect(() => {
    fetchOfficerRoles()
      .then(setRoles)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const reload = useCallback(() => {
    fetchOfficerList(query)
      .then((body) => {
        setList(body)
        setMock(isOfficerMockActive())
        setError('')
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [query])

  useEffect(reload, [reload])

  useEffect(() => {
    if (currentMode() !== 'officer') return
    const path = showCriteria
      ? `/officer/criteria/${criteriaProgram}`
      : open ? `/officer/${encodeURIComponent(query.role)}/review/${open.id}`
        : query.role === DEFAULT_QUERY.role ? '/officer' : `/officer/${encodeURIComponent(query.role)}`
    const params: Record<string, string | null> = {
      page: query.page === DEFAULT_QUERY.page ? null : String(query.page ?? 1),
      page_size: query.page_size === DEFAULT_QUERY.page_size ? null : String(query.page_size ?? 20),
      slot: open?.slot ?? null,
    }
    for (const key of QUERY_KEYS) params[key === 'ai_status' ? 'ai' : key] = query[key] ?? null
    routeUrl(path, params, initialUrlWrite.current)
    initialUrlWrite.current = false
  }, [query, open, showCriteria, criteriaProgram])

  const patch = (next: Partial<OfficerListQuery>) => {
    setQuery((prev) => ({ ...prev, ...next }))
    setSelected([])
  }

  /** 역할을 바꾸면 관할 선택은 백엔드가 다시 정해준다 — 여기서는 비워 보낸다. */
  const switchRole = (role: string) => {
    setOpen(null)
    setShowCriteria(false)
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
        {/* 목업을 보고 있다는 사실을 숨기지 않는다. 이 배너가 없으면 시연을 보는
            사람이 실제 접수 건으로 오해한다. */}
        {mock && (
          <p className="officer__mock">
            <strong>목업 데이터</strong> 실제 접수 건이 없어 예시로 채운 화면입니다. 판단
            버튼은 눌리지만 브라우저 메모리에만 남고 새로고침하면 되돌아갑니다.
            <code>?mock=0</code>을 붙이면 실제 데이터만 봅니다.
          </p>
        )}
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
        {query.role === 'province' && <button type="button" className="officer__criteria-tab" onClick={() => setShowCriteria((v) => !v)}>
          {showCriteria ? '접수 목록' : '심사 기준'}
        </button>}
        {activeRole && (
          <ul className="officer__notes">
            {activeRole.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}
      </header>

      {error && <p className="officer__error">{error}</p>}

      {showCriteria && query.role === 'province' ? (
        <>
          <label className="officer__criteria-select">사업 선택
            <select value={criteriaProgram} onChange={(e) => setCriteriaProgram(e.target.value)}>
              <option value="double_savings">전북청년 함께 두배적금</option>
              <option value="job_package">청년 취업지원 패키지</option>
            </select>
          </label>
          <CriteriaEditor code={criteriaProgram} />
        </>
      ) : open !== null ? (
        <ReviewDetail
          // 같은 건의 다른 서류로 다시 들어올 때 초기 탭 선택이 확실히 다시 돌게
          // 하는 값싼 보험이다.
          key={`${open.id}:${open.slot ?? ''}`}
          applicationId={open.id}
          role={query.role}
          initialSlotKey={open.slot}
          onBack={() => setOpen(null)}
          onDecided={reload}
        />
      ) : list ? (
        <ApplicationList
          list={list}
          query={query}
          onQuery={patch}
          onOpen={(id, slot) => setOpen({ id, slot: slot ?? null })}
          selected={selected}
          onSelect={setSelected}
          onBulk={bulk}
          busy={busy}
        />
      ) : showListSkeleton ? (
        <Skeleton className="officer__table-skeleton">
          <div className="filters officer__filters-skeleton">{['사업', '처리상태', 'AI판정', '신청일', '정렬'].map((label) => <label key={label}>{label}<SkeletonBlock className="officer__filter-control" /></label>)}</div>
          <div className="bulk officer__bulk-skeleton"><span>선택 0건</span><button type="button" className="btn" disabled aria-disabled="true">일괄 처리</button><button type="button" className="btn" disabled aria-disabled="true">일괄 확인</button></div>
          <div className="grid-scroll"><div className="officer__table-skeleton-grid">
            <div className="officer__table-skeleton-head">{['순위', '접수번호', '신청자', '지역', '서류', 'AI 판정', '점수', '상태', '접수일', '기타', '기타', '기타'].map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}</div>
            {Array.from({ length: 8 }, (_, row) => <div className="officer__table-skeleton-row" key={row}>{Array.from({ length: 12 }, (_, col) => <SkeletonLine key={col} width={col === 2 ? '78%' : '64%'} />)}</div>)}
          </div></div>
        </Skeleton>
      ) : null}
    </div>
  )
}
