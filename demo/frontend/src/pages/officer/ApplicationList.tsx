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

import type {
  OfficerList,
  OfficerListQuery,
  DecisionKey,
  OfficerRow,
  OfficerRowDoc,
} from '../../api.ts'
import { badgeClass, dotClass, shortTime } from './format.ts'

/** 서류 컬럼 키의 접두사. 서버의 `DOC_COLUMN_PREFIX`와 같은 값이다. */
const DOC_PREFIX = 'doc:'

/**
 * 서류 칸 하나 (`doc:<slot_key>` 컬럼).
 *
 * 담당자가 목록에서 재는 것은 "미비 3건"이 아니라 **어느 서류가 걸렸는가**다.
 * 그래서 칸을 눌러 바로 그 원본으로 가는 것이 이 컬럼의 전부다 — 누르면 상세가
 * 그 서류 탭을 연 채로 열린다. 여기서 파일을 내려받는 길은 만들지 않는다 (R4.1).
 *
 * 고정 4칸(초본·건보료·자격확인·자격득실)은 헤더가 서류명을 쥐므로 점만 찍는다.
 * `근로확인서류`와 `기타`만 서류명을 같이 찍는다 — 사람마다 다른 칸이라 이름이
 * 없으면 무슨 서류인지 알 수 없다.
 */
function DocCell({
  row,
  columnKey,
  onOpenDoc,
}: {
  row: OfficerRow
  columnKey: string
  onOpenDoc: (applicationId: number, slotKey: string) => void
}) {
  // 서류 컬럼은 두배적금 체크리스트를 기준으로 짜여 있다. 사업 필터가 `전체`일 때
  // 섞여 들어오는 다른 사업 행은 서버가 빈 배열을 준다 — 빈 칸으로 두면 "안 냈다"로
  // 읽히므로 해당 없음을 명시한다.
  if (!row.documents || row.documents.length === 0) {
    return (
      <td className="officer-grid__doc officer-grid__doc--na" title={`${row.program_name}에는 없는 서류입니다`}>
        —
      </td>
    )
  }

  const slot = columnKey.slice(DOC_PREFIX.length)
  const cells = row.documents.filter((d) => d.column === slot)
  if (cells.length === 0) return <td className="officer-grid__doc" />

  return (
    <td className="officer-grid__doc" onClick={(e) => e.stopPropagation()}>
      {cells.map((cell) => (
        // 미배정 병합 페이지는 여러 장이 **같은 slot_key**로 온다. 슬롯만으로
        // 키를 잡으면 `기타` 칸에서 키가 겹쳐 리액트가 칸을 잘못 재사용한다.
        <DocMark
          key={`${cell.slot_key}:${cell.document_id ?? 'none'}`}
          row={row}
          cell={cell}
          onOpenDoc={onOpenDoc}
        />
      ))}
    </td>
  )
}

function DocMark({
  row,
  cell,
  onOpenDoc,
}: {
  row: OfficerRow
  cell: OfficerRowDoc
  onOpenDoc: (applicationId: number, slotKey: string) => void
}) {
  const title = `${cell.label} — ${cell.status_label}`

  // 아직 안 낸 서류는 열 원본이 없다. 버튼으로 두면 키보드 이동에 눌리지 않는
  // 정거장이 행마다 여러 개 생긴다 — 표 하나에 그런 칸이 6개다.
  if (cell.document_id === null) {
    return (
      <span className="docmark docmark--none" title={title}>
        <span className="tabdot tabdot--none" />
        {cell.short_label && <span className="docmark__name">{cell.short_label}</span>}
      </span>
    )
  }

  return (
    <button
      type="button"
      className="docmark docmark--open"
      title={`${title} (누르면 원본을 엽니다)`}
      aria-label={title}
      onClick={() => onOpenDoc(row.application_id, cell.slot_key)}
    >
      <span className={dotClass(cell.status)} />
      {cell.short_label && <span className="docmark__name">{cell.short_label}</span>}
    </button>
  )
}

/**
 * 컬럼 한 칸.
 *
 * 헤더와 셀이 **같은 배열**(`list.columns`)을 따라야 한다. 예전에는 헤더만
 * 서버가 주는 컬럼을 쓰고 셀은 여기 하드코딩돼 있었는데, 그러면 사업마다 컬럼이
 * 달라질 때 헤더와 값이 어긋난다. 취업패키지는 점수 칸 대신 신청 항목이 온다.
 */
function Cell({
  row,
  column,
  onOpenDoc,
}: {
  row: OfficerRow
  column: { key: string }
  onOpenDoc: (applicationId: number, slotKey: string) => void
}) {
  // 서류 컬럼은 `switch` 앞에서 가른다. `default`에 두면 "모르는 컬럼은 `-`"라는
  // 기존 안전망과 뒤섞여, 컬럼 키 오타가 조용히 빈 칸이 된다.
  if (column.key.startsWith(DOC_PREFIX)) {
    return <DocCell row={row} columnKey={column.key} onOpenDoc={onOpenDoc} />
  }

  switch (column.key) {
    case 'application_no':
      return <td className="officer-grid__no">{row.application_no}</td>
    case 'name':
      return <td>{row.name}</td>
    case 'region':
      return (
        <td>
          {row.region} {row.town}
        </td>
      )
    case 'items':
      return <td className="officer-grid__items">{row.items_label || '-'}</td>
    case 'ai_status':
      return (
        <td>
          <span className={badgeClass(row.ai_status)}>{row.ai_status_label}</span>
        </td>
      )
    case 'total_score':
      return <td className="officer-grid__score">{row.total_score === null ? '-' : `${row.total_score}`}</td>
    case 'missing_count':
      return (
        <td className={row.missing_count > 0 ? 'officer-grid__missing' : undefined}>
          {row.missing_count}
        </td>
      )
    case 'submitted_at':
      return <td>{shortTime(row.submitted_at)}</td>
    case 'decision':
      return <td>{row.decision_label}</td>
    default:
      return <td>-</td>
  }
}

interface Props {
  list: OfficerList
  query: OfficerListQuery
  onQuery: (patch: Partial<OfficerListQuery>) => void
  /**
   * 상세 열기. `slotKey`가 있으면 상세가 그 서류 탭을 연 채로 시작한다 —
   * 목록의 서류 칸을 눌러 들어오는 경로다.
   */
  onOpen: (applicationId: number, slotKey?: string) => void
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

      {/* 시군별 정원은 점수제 사업에만 있는 개념이다. 선착순 사업에서는 서버가
          빈 배열을 주므로 배지 줄 자체를 그리지 않는다. */}
      {list.quota.length > 0 && (
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
      )}

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

      <div className="officer-grid-scroll">
        <table className="officer-grid">
        <thead>
          <tr>
            {list.role.can_bulk && (
              <th className="officer-grid__check">
                <input
                  type="checkbox"
                  aria-label="전체 선택"
                  checked={allChecked}
                  onChange={() => onSelect(allChecked ? [] : allIds)}
                />
              </th>
            )}
            <th>{list.rank_label ?? '순위'}</th>
            {list.columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.rows.map((row) => (
            <tr key={row.application_id} onClick={() => onOpen(row.application_id)}>
              {list.role.can_bulk && (
                <td className="officer-grid__check" onClick={(e) => e.stopPropagation()}>
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
              <td className="officer-grid__rank">{row.rank ?? '-'}</td>
              {list.columns.map((c) => (
                <Cell key={c.key} row={row} column={c} onOpenDoc={onOpen} />
              ))}
            </tr>
          ))}
          {list.rows.length === 0 && (
            <tr>
              <td className="officer-grid__empty" colSpan={list.columns.length + 2}>
                조건에 맞는 접수 건이 없습니다.
              </td>
            </tr>
          )}
        </tbody>
        </table>
      </div>

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
