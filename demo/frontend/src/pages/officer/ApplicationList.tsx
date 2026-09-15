/**
 * 접수 목록 (R4.4).
 *
 * 컬럼은 계획서 3.2절 [A] 정의 그대로다. 두배적금은 점수순, 취업패키지는 접수순이
 * 기본 정렬인데, 선발 방식이 점수제와 선착순으로 다르기 때문이다.
 *
 * 시군별 정원 대비 진행률 배지가 목록 위에 온다 — 담당자가 "지금 몇 명 찼고
 * 커트라인이 어디인가"를 목록을 훑기 전에 먼저 본다. 통계·시각화는 대시보드
 * 영역이고, 이 배지까지가 데모 담당자 화면의 경계선이다 (C4).
 */

import type { OfficerList, OfficerListQuery, DecisionKey } from '../../api.ts'
import { badgeClass, shortTime } from './format.ts'

interface Props {
  list: OfficerList
  query: OfficerListQuery
  onQuery: (patch: Partial<OfficerListQuery>) => void
  onOpen: (applicationId: number) => void
  selected: number[]
  onSelect: (ids: number[]) => void
  onBulk: (decision: DecisionKey) => void
  busy: boolean
}

export default function ApplicationList({
  list,
  query,
  onQuery,
  onOpen,
  selected,
  onSelect,
  onBulk,
  busy,
}: Props) {
  const allIds = list.rows.map((r) => r.application_id)
  const allChecked = allIds.length > 0 && allIds.every((id) => selected.includes(id))

  return (
    <div className="list">
      {/* 선착순 사업을 고르면 시군 정원 대신 총 지원규모 대비 접수 진행률을 본다.
          선발 방식이 다르므로 같은 배지를 쓸 수 없다. */}
      {list.first_come && (
        <div className="fcfs">
          <span className="fcfs__name">{list.first_come.program_name}</span>
          <span className="fcfs__count">
            접수 {list.first_come.applied.toLocaleString('ko-KR')} /{' '}
            {list.first_come.quota.toLocaleString('ko-KR')}건
          </span>
          <span className="fcfs__bar">
            <i style={{ width: `${Math.min(100, list.first_come.rate_percent)}%` }} />
          </span>
          <span className="fcfs__meta">
            선정 {list.first_come.selected}건 · 남은 규모 {list.first_come.remaining}건
            {list.first_come.supplement_days !== null && (
              <> · 보완 {list.first_come.supplement_days}일</>
            )}
          </span>
          <span className="fcfs__notice">{list.first_come.notice}</span>
        </div>
      )}

      <div className="quota">
        {list.quota.map((q) => (
          <div key={q.region} className="quota__item">
            <span className="quota__region">{q.region}</span>
            <span className="quota__count">
              {q.selected} / {q.quota}
            </span>
            <span className="quota__bar">
              <i style={{ width: `${Math.min(100, (q.selected / q.quota) * 100)}%` }} />
            </span>
            <span className="quota__meta">
              접수 {q.applied}건
              {q.role_cutoff !== null && <> · 커트라인 {q.role_cutoff}점</>}
              {list.role.quota_ratio === 1.2 && <> · 120% {q.limit_120}명</>}
            </span>
          </div>
        ))}
      </div>

      <div className="filters">
        <label>
          사업
          <select
            value={query.program ?? ''}
            onChange={(e) => onQuery({ program: e.target.value, page: 1 })}
          >
            <option value="">전체</option>
            {list.filters.programs.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        {list.scope.region_locked && (
          <label>
            시군
            <select
              value={list.scope.region}
              onChange={(e) => onQuery({ region: e.target.value, town: '', page: 1 })}
            >
              {list.scope.regions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
        )}

        {list.scope.town_locked && (
          <label>
            읍·면·동
            <select
              value={list.scope.town}
              onChange={(e) => onQuery({ town: e.target.value, page: 1 })}
            >
              {list.scope.towns.length === 0 && <option value="">(접수 없음)</option>}
              {list.scope.towns.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        )}

        <label>
          처리상태
          <select
            value={query.status ?? ''}
            onChange={(e) => onQuery({ status: e.target.value, page: 1 })}
          >
            <option value="">전체</option>
            {list.filters.statuses.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          AI판정
          <select
            value={query.ai_status ?? ''}
            onChange={(e) => onQuery({ ai_status: e.target.value, page: 1 })}
          >
            <option value="">전체</option>
            {list.filters.ai_statuses.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          신청일
          <input
            type="date"
            aria-label="신청일 시작"
            value={query.submitted_from ?? ''}
            onChange={(e) => onQuery({ submitted_from: e.target.value, page: 1 })}
          />
          <span className="filters__tilde">~</span>
          <input
            type="date"
            aria-label="신청일 종료"
            value={query.submitted_to ?? ''}
            onChange={(e) => onQuery({ submitted_to: e.target.value, page: 1 })}
          />
        </label>

        <label>
          정렬
          <select
            value={query.sort ?? list.filters.applied.sort ?? 'score'}
            onChange={(e) => onQuery({ sort: e.target.value, page: 1 })}
          >
            {list.filters.sorts.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <span className="filters__total">{list.total}건</span>
      </div>

      {list.role.can_bulk ? (
        <div className="bulk">
          <span>선택 {selected.length}건</span>
          {list.role.actions.map((a) => (
            <button
              key={a.key}
              type="button"
              className={`btn btn--${a.tone}`}
              disabled={busy || selected.length === 0}
              onClick={() => onBulk(a.key)}
            >
              일괄 {a.result_label}
            </button>
          ))}
        </div>
      ) : (
        <p className="bulk bulk--off">
          {list.role.name}은 구비서류를 건별로 확인하는 단계라 일괄 처리를 제공하지 않습니다.
        </p>
      )}

      <table className="grid">
        <thead>
          <tr>
            {list.role.can_bulk && (
              <th className="grid__check">
                <input
                  type="checkbox"
                  aria-label="전체 선택"
                  checked={allChecked}
                  onChange={() => onSelect(allChecked ? [] : allIds)}
                />
              </th>
            )}
            <th>순위</th>
            {list.columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.rows.map((row) => (
            <tr key={row.application_id} onClick={() => onOpen(row.application_id)}>
              {list.role.can_bulk && (
                <td className="grid__check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`${row.application_no} 선택`}
                    checked={selected.includes(row.application_id)}
                    onChange={() =>
                      onSelect(
                        selected.includes(row.application_id)
                          ? selected.filter((id) => id !== row.application_id)
                          : [...selected, row.application_id],
                      )
                    }
                  />
                </td>
              )}
              <td className="grid__rank">{row.rank ?? '-'}</td>
              <td className="grid__no">{row.application_no}</td>
              <td>{row.name}</td>
              <td>
                {row.region} {row.town}
              </td>
              <td>
                <span className={badgeClass(row.ai_status)}>{row.ai_status_label}</span>
              </td>
              <td className="grid__score">
                {row.total_score === null ? '-' : `${row.total_score}`}
              </td>
              <td className={row.missing_count > 0 ? 'grid__missing' : undefined}>
                {row.missing_count}
              </td>
              <td>{shortTime(row.submitted_at)}</td>
              <td>{row.decision_label}</td>
            </tr>
          ))}
          {list.rows.length === 0 && (
            <tr>
              <td className="grid__empty" colSpan={list.columns.length + 2}>
                조건에 맞는 접수 건이 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {list.page_count > 1 && (
        <div className="pager">
          {Array.from({ length: list.page_count }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              type="button"
              className={p === list.page ? 'pager__on' : undefined}
              onClick={() => onQuery({ page: p })}
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
