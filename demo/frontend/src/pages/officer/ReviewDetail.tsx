/**
 * 분할 심사 뷰 — 좌 55% 원본 / 우 45% AI 판독 결과 (R4.2).
 *
 * 이 화면의 차별점은 **판정 근거와 원본 위치가 이어져 있다**는 것이다. 심사표
 * 항목이나 판독 필드를 클릭하면 좌측 뷰어가 해당 서류의 해당 좌표로 스크롤하고
 * 그 자리를 하이라이트한다 (R4.3). "소득분위 초과"라고만 쓰면 담당자는 결국 원본
 * 파일을 찾아 헤맨다.
 *
 * 화면 어디에도 파일을 내려받는 버튼이 없다 (R4.1).
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  fetchReviewDetail,
  postDecision,
  type BBox,
  type DecisionKey,
  type OfficerDocument,
  type ReviewDetailData,
  type ScoreItemRow,
} from '../../api.ts'
import DocumentViewer from './DocumentViewer.tsx'
import { badgeClass, dotClass } from './format.ts'
import ScoreSheet6 from './ScoreSheet6.tsx'

interface Props {
  applicationId: number
  role: string
  onBack: () => void
  /** 판단이 기록되면 목록을 다시 읽어야 한다. */
  onDecided: () => void
}

interface Focus {
  documentId: number
  bbox: BBox | null
  label: string
  scoreKey: string | null
}

export default function ReviewDetail({ applicationId, role, onBack, onDecided }: Props) {
  const [detail, setDetail] = useState<ReviewDetailData | null>(null)
  const [error, setError] = useState('')
  const [activeDocId, setActiveDocId] = useState<number | null>(null)
  const [focus, setFocus] = useState<Focus | null>(null)
  const [memo, setMemo] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => {
    fetchReviewDetail(applicationId, role)
      .then((d) => {
        setDetail(d)
        setMemo(d.decision.memo ?? '')
        setActiveDocId((prev) => prev ?? d.documents[0]?.document_id ?? null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

  useEffect(load, [applicationId, role])

  const activeDoc: OfficerDocument | null = useMemo(() => {
    if (!detail) return null
    return (
      detail.documents.find((d) => d.document_id === activeDocId) ?? detail.documents[0] ?? null
    )
  }, [detail, activeDocId])

  if (error) return <p className="officer__error">{error}</p>
  if (!detail || !activeDoc) return <p className="officer__loading">심사 정보를 불러오는 중…</p>

  /** 심사표 항목 → 좌측 원본의 해당 위치. */
  const focusScoreItem = (item: ScoreItemRow) => {
    if (!item.source_document_id) return
    setActiveDocId(item.source_document_id)
    setFocus({
      documentId: item.source_document_id,
      bbox: item.bbox,
      label: `${item.label} ${item.score}점`,
      scoreKey: item.key,
    })
  }

  /** 판독 필드 → 좌측 원본의 해당 위치. */
  const focusField = (doc: OfficerDocument, field: string) => {
    const bbox = doc.bboxes[field]
    if (!bbox) return
    setActiveDocId(doc.document_id)
    setFocus({ documentId: doc.document_id, bbox, label: field, scoreKey: null })
  }

  const decide = (decision: DecisionKey) => {
    setSaving(true)
    postDecision(applicationId, { role, decision, memo })
      .then(() => {
        load()
        onDecided()
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSaving(false))
  }

  const highlight = focus && focus.documentId === activeDoc.document_id ? focus.bbox : null

  return (
    <div className="review">
      <header className="review__head">
        <button type="button" className="review__back" onClick={onBack}>
          ← 접수 목록
        </button>
        <span className="review__no">{detail.application_no}</span>
        <strong className="review__name">{detail.name}</strong>
        <span className="review__where">
          {detail.region} {detail.town}
        </span>
        <span className="review__when">접수 {detail.submitted_at ?? '-'}</span>
        <span className={badgeClass(detail.ai.final_status)}>{detail.ai.final_status_label}</span>
        {detail.score_sheet.items.length > 0 && (
          <span className="review__score">
            {detail.score_sheet.total} / {detail.score_sheet.max_total}점
          </span>
        )}
        <span className="review__spacer" />
        <span className="review__role">{detail.role.name} 화면</span>
      </header>

      <div className="review__split">
        {/* ---------------- 좌 55% 원본 ---------------- */}
        <section className="review__left">
          <nav className="review__tabs">
            {detail.documents.map((d) => (
              <button
                key={d.document_id}
                type="button"
                className={
                  d.document_id === activeDoc.document_id
                    ? 'review__tab review__tab--on'
                    : 'review__tab'
                }
                onClick={() => setActiveDocId(d.document_id)}
              >
                <span className={dotClass(d.status)} />
                {d.label}
              </button>
            ))}
          </nav>
          <DocumentViewer
            doc={activeDoc}
            highlight={highlight}
            highlightLabel={focus?.label}
          />
        </section>

        {/* ---------------- 우 45% 판독 결과 ---------------- */}
        <section className="review__right">
          <Panel title="최종 판정">
            <div className="verdict">
              <span className={badgeClass(detail.ai.final_status)}>
                {detail.ai.final_status_label}
              </span>
              <span className="verdict__action">{detail.ai.recommended_action}</span>
            </div>
            <ul className="verdict__stages">
              <li>1단계 서류 적합성: {detail.ai.stage1_status ?? '-'}</li>
              <li>2단계 통합 자격심사: {detail.ai.stage2_status ?? '-'}</li>
            </ul>
            {detail.ai.reasons.length > 0 ? (
              <ul className="reasons">
                {detail.ai.reasons.map((r, i) => (
                  <li key={i}>
                    <code>{r.code}</code> {r.message}
                    {r.doc_type && <em> ({r.doc_type})</em>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">부적합·확인필요 사유가 없습니다.</p>
            )}
          </Panel>

          <Panel title="심사표 (서식6)">
            <ScoreSheet6
              sheet={detail.score_sheet}
              activeKey={focus?.scoreKey ?? null}
              onSelect={focusScoreItem}
            />
          </Panel>

          <Panel title="자격요건 체크리스트">
            <ul className="checks">
              {detail.eligibility.map((e) => (
                <li key={e.key} className={e.ok ? 'checks__ok' : 'checks__no'}>
                  <span className="checks__mark">{e.ok ? '✓' : '✕'}</span>
                  <span>
                    <strong>{e.label}</strong>
                    <em>{e.basis}</em>
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="제외대상 조회 결과">
            <ul className="checks">
              {detail.exclusions.map((x, i) => (
                <li key={i} className={x.ok ? 'checks__ok' : 'checks__no'}>
                  <span className="checks__mark">{x.ok ? '✓' : '✕'}</span>
                  <span>
                    <strong>
                      {x.label} — {x.answer}
                    </strong>
                    <em>{x.source}</em>
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title={`판독 결과 — ${activeDoc.label}`}>
            <dl className="ocr">
              <dt>판별된 서류</dt>
              <dd>
                {activeDoc.detected_doc_type ?? '판별 실패'}
                {activeDoc.expected_doc_type &&
                  activeDoc.expected_doc_type !== activeDoc.detected_doc_type && (
                    <em> (요구: {activeDoc.expected_doc_type})</em>
                  )}
              </dd>
              <dt>판독 신뢰도</dt>
              <dd>
                {activeDoc.ocr_confidence === null
                  ? '-'
                  : `${Math.round(activeDoc.ocr_confidence * 100)}%`}{' '}
                <em>({activeDoc.ocr_tier})</em>
              </dd>
              <dt>입력한 발급일</dt>
              <dd>{activeDoc.declared_issue_date ?? '-'}</dd>
            </dl>
            <ul className="fields">
              {Object.entries(activeDoc.extracted).map(([key, value]) => (
                <li key={key}>
                  <span className="fields__key">{key}</span>
                  <span className="fields__value">{value}</span>
                  {activeDoc.bboxes[key] && (
                    <button
                      type="button"
                      className="fields__go"
                      onClick={() => focusField(activeDoc, key)}
                    >
                      원본 위치
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {activeDoc.findings.length > 0 && (
              <ul className="reasons">
                {activeDoc.findings.map((f, i) => (
                  <li key={i}>
                    <code>{f.code}</code> {f.message}
                    {f.how_to_fix && <em> {f.how_to_fix}</em>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="담당자 처리">
            <p className="muted">
              {detail.role.name} · {detail.role.stage} — {detail.role.scope}
            </p>
            {detail.decision.decision && (
              <p className="decided">
                현재 처리 상태: <strong>{detail.decision.label}</strong>{' '}
                <em>{detail.decision.decided_at}</em>
              </p>
            )}
            <textarea
              className="memo"
              value={memo}
              rows={3}
              placeholder="담당자 메모 (판단 근거·확인 사항)"
              aria-label="담당자 메모"
              onChange={(e) => setMemo(e.target.value)}
            />
            <div className="actions">
              {detail.role.actions.map((a) => (
                <button
                  key={a.key}
                  type="button"
                  className={`btn btn--${a.tone}`}
                  disabled={saving}
                  onClick={() => decide(a.key)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </Panel>
        </section>
      </div>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h3 className="panel__title">{title}</h3>
      <div className="panel__body">{children}</div>
    </section>
  )
}
