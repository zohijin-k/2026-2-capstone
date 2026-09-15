/**
 * 지원 항목 선택 · 예상 지원금 (P5).
 *
 * 사업계획서가 "면접비, 정장비, 사진비, 자격증 응시료 지원(복수선택가능)"이라
 * 적었으므로, 이 화면의 입력은 항목 하나가 아니라 **항목 × 회차 × 영수증 금액**이다.
 *
 * 화면이 지키는 것 둘:
 *   1. 고르는 즉시 추가서류가 몇 장 늘어나는지 보인다 (R6.3)
 *   2. 영수증을 적는 즉시 **실지급액과 그 계산 근거**가 보인다 (R6.2)
 *      — "70,000원 결제했는데 왜 50,000원인가"를 묻지 않게 하는 것이 전부다.
 */

import { useEffect, useState } from 'react'

import {
  fetchSubsidyItems,
  saveSubsidyItems,
  type SubsidyCatalogItem,
  type SubsidySelection,
  type SubsidyState,
} from '../../api.ts'
import './subsidy-items.css'

const won = (value: number) => `${value.toLocaleString('ko-KR')}원`

/** 화면 상태: 항목별 회차와 회차별 영수증 금액 문자열. */
type Draft = Record<string, { count: number; receipts: string[] }>

function toDraft(catalog: SubsidyCatalogItem[], selections: SubsidySelection[]): Draft {
  const draft: Draft = {}
  for (const item of catalog) {
    const hit = selections.find((s) => s.item_type === item.item_type)
    draft[item.item_type] = {
      count: hit?.count ?? 0,
      receipts: Array.from({ length: item.max_count }, (_, i) => {
        const value = hit?.receipts[i]
        return value === null || value === undefined ? '' : String(value)
      }),
    }
  }
  return draft
}

function toSelections(draft: Draft): SubsidySelection[] {
  return Object.entries(draft)
    .filter(([, v]) => v.count > 0)
    .map(([item_type, v]) => ({
      item_type,
      count: v.count,
      receipts: v.receipts.slice(0, v.count).map((r) => (r === '' ? null : Number(r))),
    }))
}

function ItemCard({
  item,
  draft,
  onCount,
  onReceipt,
}: {
  item: SubsidyCatalogItem
  draft: { count: number; receipts: string[] }
  onCount: (count: number) => void
  onReceipt: (index: number, value: string) => void
}) {
  const counts = Array.from({ length: item.max_count + 1 }, (_, i) => i)
  const picked = draft.count > 0

  return (
    <li className={picked ? 'sitem sitem--on' : 'sitem'}>
      <div className="sitem__head">
        <label className="sitem__check">
          <input
            type="checkbox"
            checked={picked}
            onChange={(e) => onCount(e.target.checked ? 1 : 0)}
          />
          <span className="sitem__label">{item.label}</span>
        </label>
        <span className="sitem__amount">{item.amount_label}</span>
        <span className="sitem__count">{item.count_label}</span>
      </div>

      <p className="sitem__desc">{item.description}</p>
      <p className="sitem__note">{item.note}</p>

      {picked && (
        <div className="sitem__body">
          {item.max_count > 1 && (
            <label className="sitem__pick">
              신청 횟수
              <select
                value={draft.count}
                onChange={(e) => onCount(Number(e.target.value))}
              >
                {counts
                  .filter((c) => c > 0)
                  .map((c) => (
                    <option key={c} value={c}>
                      {c}회
                    </option>
                  ))}
              </select>
            </label>
          )}

          {item.needs_receipt ? (
            <div className="sitem__receipts">
              {Array.from({ length: draft.count }, (_, i) => (
                <label key={i} className="sitem__receipt">
                  {item.max_count > 1 ? `${i + 1}회차 ` : ''}결제영수증 금액
                  <input
                    inputMode="numeric"
                    value={draft.receipts[i] ?? ''}
                    aria-label={`${item.label} ${i + 1}회차 결제영수증 금액`}
                    onChange={(e) => onReceipt(i, e.target.value.replace(/\D/g, ''))}
                  />
                  <span>원</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="sitem__fixed">
              영수증이 필요 없습니다. 면접확인서만 올리면 회당 {won(item.unit_cap)}이
              정액 지급됩니다.
            </p>
          )}

          <p className="sitem__docs">
            추가서류: {item.extra_docs.join(' + ')}
            {item.max_count > 1 && draft.count > 1 && ` (회차마다 각각)`}
          </p>
        </div>
      )}
    </li>
  )
}

export default function SubsidyItems({
  applicationId,
  onChanged,
}: {
  applicationId: number
  /** 저장이 끝났을 때. 상위가 서류 체크리스트를 다시 읽는다. */
  onChanged?: (state: SubsidyState) => void
}) {
  const [state, setState] = useState<SubsidyState | null>(null)
  const [draft, setDraft] = useState<Draft>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchSubsidyItems(applicationId)
      .then((s) => {
        setState(s)
        setDraft(toDraft(s.catalog, s.selections))
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [applicationId])

  /** 입력이 바뀔 때마다 서버에 저장한다. 지급액 계산은 서버가 단일 소스다. */
  const save = (next: Draft) => {
    setDraft(next)
    setBusy(true)
    saveSubsidyItems(applicationId, toSelections(next))
      .then((s) => {
        setState(s)
        onChanged?.(s)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  if (error && !state) return <p className="flow-error">{error}</p>
  if (!state) return <p className="subsidy__loading">지원 항목을 불러오는 중…</p>

  const estimate = state.estimate

  return (
    <div className="subsidy">
      <section className="subsidy__intro">
        <h3>지원받을 항목을 고르세요 (복수 선택 가능)</h3>
        <p>{state.notice}</p>
      </section>

      <ul className="sitems">
        {state.catalog.map((item) => (
          <ItemCard
            key={item.item_type}
            item={item}
            draft={draft[item.item_type] ?? { count: 0, receipts: [] }}
            onCount={(count) =>
              save({
                ...draft,
                [item.item_type]: {
                  count,
                  receipts: draft[item.item_type]?.receipts ?? [],
                },
              })
            }
            onReceipt={(index, value) => {
              const current = draft[item.item_type] ?? { count: 0, receipts: [] }
              const receipts = [...current.receipts]
              receipts[index] = value
              save({ ...draft, [item.item_type]: { ...current, receipts } })
            }}
          />
        ))}
      </ul>

      <section className="subsidy__sum">
        <h3>예상 지원금 {busy && <span className="subsidy__busy">계산 중…</span>}</h3>
        {estimate.lines.length === 0 ? (
          <p className="subsidy__empty">아직 고른 항목이 없습니다.</p>
        ) : (
          <>
            <table className="subsidy__table">
              <thead>
                <tr>
                  <th>항목</th>
                  <th>영수증 금액</th>
                  <th>지급 예정액</th>
                  <th>계산 근거</th>
                </tr>
              </thead>
              <tbody>
                {estimate.lines.map((line) => (
                  <tr
                    key={`${line.item_type}-${line.index}`}
                    className={line.pending ? 'is-pending' : undefined}
                  >
                    <td>{line.label}</td>
                    <td className="subsidy__num">
                      {line.actual_cost
                        ? line.receipt_amount === null
                          ? '미입력'
                          : won(line.receipt_amount)
                        : '불요'}
                    </td>
                    <td className="subsidy__num subsidy__granted">
                      {won(line.granted_amount)}
                    </td>
                    <td className="subsidy__basis">{line.calculation}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th colSpan={2}>합계</th>
                  <td className="subsidy__num subsidy__total">
                    {won(estimate.total_granted)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>

            {estimate.warnings.map((w) => (
              <p key={w} className="subsidy__warn">
                {w}
              </p>
            ))}
            {estimate.pending && (
              <p className="subsidy__warn">
                결제영수증 금액을 입력해야 지급 예정액이 확정됩니다.
              </p>
            )}
          </>
        )}
      </section>

      {error && <p className="subsidy__error">{error}</p>}
    </div>
  )
}
