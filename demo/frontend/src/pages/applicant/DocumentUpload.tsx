/**
 * 서류 업로드 · 즉시 판정 (P2).
 *
 * 두배적금은 보완 요청이 없는 사업이다. 제출한 뒤에 미비를 알려주면 이미 늦다.
 * 그래서 이 화면의 전부는 "올리는 순간 알려준다"에 걸려 있다.
 *
 *   근로유형 선택 → 본인에게 필요한 서류만 남는다 (R3.2)
 *   슬롯마다  [발급처 바로가기] [파일 선택] [발급일 직접 입력]
 *   업로드 즉시 적합 / 부적합 / 확인필요 + 사유 + 해결 방법 + 재업로드 (R2.1·R2.2)
 */

import { useEffect, useRef, useState } from 'react'

import {
  deleteDocument,
  fetchChecklist,
  putDocContext,
  uploadDocument,
  type Checklist,
  type DocRequirementRow,
  type DocStatus,
  type UploadedDocument,
} from '../../api.ts'
import Modal from '../../components/Modal.tsx'
import { Checks, DateTriple } from '../../forms/FormSheet.tsx'
import { EMPTY_YMD, ymdToISO, type YMD } from '../../forms/ymd.ts'
import './document-upload.css'

const STATUS_LABEL: Record<DocStatus, string> = {
  PASS: '적합',
  FAIL: '부적합',
  NEEDS_REVIEW: '확인필요',
}

const WORKPLACE_COUNTS = ['1개', '2개', '3개'] as const

function StatusBadge({ status }: { status: DocStatus }) {
  return <span className={`dstatus dstatus--${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>
}

function DocumentResult({
  doc,
  onRetry,
}: {
  doc: UploadedDocument
  onRetry: () => void
}) {
  const status = doc.status ?? 'NEEDS_REVIEW'
  const extracted = Object.entries(doc.extracted)
  return (
    <div className={`dresult dresult--${status.toLowerCase()}`}>
      <div className="dresult__head">
        <StatusBadge status={status} />
        <span className="dresult__file">{doc.file_name}</span>
        {doc.detected_doc_type && (
          <span className="dresult__detected">판독: {doc.detected_doc_type}</span>
        )}
        <span className="dresult__meta">
          {doc.ocr_tier} · 신뢰도 {doc.ocr_confidence?.toFixed(2) ?? '-'} · {doc.elapsed_ms ?? 0}ms
        </span>
        <button type="button" className="btn btn--small" onClick={onRetry}>
          다시 올리기
        </button>
      </div>

      {doc.findings.map((f) => (
        <div key={f.code} className="dfinding">
          <p className="dfinding__msg">{f.message}</p>
          {f.how_to_fix && <p className="dfinding__fix">{f.how_to_fix}</p>}
          {f.link && (
            <a className="dfinding__link" href={f.link} target="_blank" rel="noreferrer">
              발급처 바로가기 ↗
            </a>
          )}
        </div>
      ))}

      {status === 'PASS' && <p className="dfinding__ok">확인이 끝났습니다.</p>}

      {extracted.length > 0 && (
        <dl className="dextract">
          {extracted.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

/** ⓘ에 보여줄 내용이 하나라도 있는지. 없으면 아이콘 자체를 띄우지 않는다. */
function hasInfo(item: DocRequirementRow): boolean {
  return (
    item.doc_type_choices.length > 1 ||
    item.required_fields.length > 0 ||
    item.notes.length > 0 ||
    item.alternatives.length > 0 ||
    item.warnings.length > 0
  )
}

/** 카드에서 뺀 요건 설명 · 체크포인트를 모아 보여주는 모달. 발급처 링크는 원래대로
    카드에 남겨 새 창으로 바로 열리게 한다 — 모달 안에 숨기지 않는다. */
function SlotInfoModal({ item, onClose }: { item: DocRequirementRow; onClose: () => void }) {
  return (
    <Modal title={item.label} onClose={onClose}>
      {item.doc_type_choices.length > 1 && (
        <div className="dinfo__section">
          <h4>인정되는 서류</h4>
          <p>{item.doc_type_choices.join(' 또는 ')} 중 하나만 올리면 됩니다.</p>
        </div>
      )}
      {item.required_fields.length > 0 && (
        <div className="dinfo__section">
          <h4>반드시 있어야 하는 표기</h4>
          <p>{item.required_fields.join('·')} 표기가 반드시 있어야 인정됩니다.</p>
        </div>
      )}
      {item.notes.length > 0 && (
        <div className="dinfo__section">
          <h4>안내</h4>
          {item.notes.map((n) => (
            <p key={n}>※ {n}</p>
          ))}
        </div>
      )}
      {item.alternatives.length > 0 && (
        <div className="dinfo__section">
          <h4>대체 가능</h4>
          {item.alternatives.map((n) => (
            <p key={n} className="dinfo__alt">
              {n}
            </p>
          ))}
        </div>
      )}
      {item.warnings.length > 0 && (
        <div className="dinfo__section">
          <h4>자주 틀리는 부분</h4>
          <ul className="dinfo__warn">
            {item.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  )
}

function SlotCard({
  item,
  busy,
  declared,
  onDeclaredChange,
  onPick,
  onRetry,
}: {
  item: DocRequirementRow
  busy: boolean
  declared: YMD
  onDeclaredChange: (v: YMD) => void
  onPick: (file: File) => void
  onRetry: (doc: UploadedDocument) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [infoOpen, setInfoOpen] = useState(false)
  const doc = item.documents[0]
  const status = doc?.status ?? null

  return (
    <li className={`dslot${status ? ` dslot--${status.toLowerCase()}` : ''}`} id={`slot-${item.slot_key}`}>
      <div className="dslot__head">
        <span className="dslot__label">{item.label}</span>
        {item.required && <span className="dslot__req">필수</span>}
        {hasInfo(item) && (
          <button
            type="button"
            className="dslot__info"
            onClick={() => setInfoOpen(true)}
            aria-label={`${item.label} 요건 안내`}
          >
            ⓘ
          </button>
        )}
        {item.issuer_url && (
          <a className="dslot__issuer" href={item.issuer_url} target="_blank" rel="noreferrer">
            {item.issuer} 바로가기 ↗
          </a>
        )}
        {status === 'PASS' && <span className="dslot__check">✓ 확인 완료</span>}
      </div>

      <div className="dslot__row">
        <input
          ref={input}
          className="dslot__file"
          type="file"
          accept={item.accept.map((f) => `.${f}`).join(',')}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onPick(file)
            e.target.value = ''
          }}
        />
        {item.check_declared_date && (
          <label className="dslot__declared">
            발급일 직접 입력
            <DateTriple value={declared} onChange={onDeclaredChange} ariaPrefix={item.label} />
          </label>
        )}
        <button
          type="button"
          className="btn btn--small"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? '판독 중…' : '파일 선택'}
        </button>
      </div>

      {doc && <DocumentResult doc={doc} onRetry={() => onRetry(doc)} />}
      {infoOpen && <SlotInfoModal item={item} onClose={() => setInfoOpen(false)} />}
    </li>
  )
}

export default function DocumentUpload({ applicationId }: { applicationId: number }) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [declared, setDeclared] = useState<Record<string, YMD>>({})
  const [busySlot, setBusySlot] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetchChecklist(applicationId)
      .then(setChecklist)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [applicationId])

  const context = checklist?.context ?? {}

  /** 근로유형 등이 바뀌면 서버가 다시 조립한 체크리스트로 통째로 갈아끼운다. */
  const changeContext = (patch: Record<string, unknown>) => {
    putDocContext(applicationId, { ...context, ...patch })
      .then(setChecklist)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

  const refresh = () => fetchChecklist(applicationId).then(setChecklist)

  const upload = async (item: DocRequirementRow, file: File) => {
    setBusySlot(item.slot_key)
    setError('')
    try {
      await uploadDocument(applicationId, item.slot_key, file, ymdToISO(declared[item.slot_key] ?? EMPTY_YMD))
      await refresh()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusySlot('')
    }
  }

  const retry = async (doc: UploadedDocument) => {
    await deleteDocument(applicationId, doc.document_id)
    await refresh()
  }

  if (error && !checklist) return <p className="flow-error">{error}</p>
  if (!checklist) return <p className="dupload__loading">서류 목록을 불러오는 중…</p>

  const uploadItems = checklist.items.filter((i) => i.upload)
  const onlineItems = checklist.items.filter((i) => !i.upload)

  return (
    <div className="dupload">
      {/* 근로확인서류가 있는 사업에서만 근로유형을 묻는다. 취업패키지는 근로요건이
          없어 이 구획 자체가 뜨지 않는다. */}
      {checklist.program.asks_work_category && (
        <section className="dupload__context">
          <h3>근로유형</h3>
          <p className="dupload__hint">
            근로확인서류는 5종 중 1종만 내면 됩니다. 아래에서 고르면 본인에게 필요한 서류만 남습니다.
          </p>
          <Checks
            name="work_category"
            options={checklist.work_categories}
            value={context.work_category ?? ''}
            onChange={(v) => changeContext({ work_category: v })}
            cols={2}
          />
          <div className="dupload__opts">
            <label>
              <input
                type="checkbox"
                checked={!!context.admin_fixed_term}
                onChange={(e) => changeContext({ admin_fixed_term: e.target.checked })}
              />
              행정기관 기간제 근로자입니다 (근로계약서 사본 추가)
            </label>
            <label>
              근무 사업장 수
              <select
                value={`${context.workplace_count ?? 1}개`}
                onChange={(e) => changeContext({ workplace_count: Number(e.target.value[0]) })}
              >
                {WORKPLACE_COUNTS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={!!context.handwritten_admin_consent}
                onChange={(e) => changeContext({ handwritten_admin_consent: e.target.checked })}
              />
              서식5를 자필서명 스캔본으로 제출하겠습니다
            </label>
          </div>
        </section>
      )}

      <div className="dupload__progress">
        제출 서류 <strong>{checklist.upload_done}</strong> / {checklist.upload_total}
        {checklist.program.asks_work_category && !context.work_category && (
          <span className="dupload__progress-hint">근로유형을 고르면 서류가 1종 추가됩니다.</span>
        )}
        {checklist.program.has_subsidy_items && (
          <span className="dupload__progress-hint">
            고르신 지원 항목에 따라 서류가 늘고 줍니다. 항목을 바꾸면 이 목록도 바뀝니다.
          </span>
        )}
        <div className="dupload__bar">
          <div
            className="dupload__bar-fill"
            style={{
              width: `${checklist.upload_total ? (checklist.upload_done / checklist.upload_total) * 100 : 0}%`,
            }}
          />
        </div>
      </div>

      <ul className="dslots">
        {uploadItems.map((item) => (
          <SlotCard
            key={item.slot_key}
            item={item}
            busy={busySlot === item.slot_key}
            declared={declared[item.slot_key] ?? EMPTY_YMD}
            onDeclaredChange={(v) => setDeclared({ ...declared, [item.slot_key]: v })}
            onPick={(file) => void upload(item, file)}
            onRetry={(doc) => void retry(doc)}
          />
        ))}
      </ul>

      {onlineItems.length > 0 && (
        <section className="dupload__online">
          <h3>업로드하지 않아도 되는 서류</h3>
          <ul>
            {onlineItems.map((i) => (
              <li key={i.slot_key}>
                <strong>{i.label}</strong> — {i.fulfilled_by}(으)로 대체되었습니다.
              </li>
            ))}
          </ul>
        </section>
      )}

      {checklist.unassigned.length > 0 && (
        <section className="dupload__unassigned">
          <h3>배정되지 않은 페이지</h3>
          <ul>
            {checklist.unassigned.map((d) => (
              <li key={d.document_id}>
                {d.file_name}
                {d.page_index !== null && ` (${d.page_index + 1}쪽)`} —{' '}
                {d.detected_doc_type ?? '서류 종류 미판별'}
                <button
                  type="button"
                  className="btn btn--small"
                  onClick={() => void retry(d)}
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {error && <p className="dupload__error">{error}</p>}
    </div>
  )
}
