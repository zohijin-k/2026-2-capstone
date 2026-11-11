/**
 * 서류 업로드 · 즉시 판정 (P2).
 *
 * 두배적금은 보완 요청이 없는 사업이다. 제출한 뒤에 미비를 알려주면 이미 늦다.
 * 그래서 이 화면의 전부는 "올리는 순간 알려준다"에 걸려 있다.
 *
 *   근로유형 선택 → 본인에게 필요한 서류만 남는다 (R3.2)
 *   슬롯마다  [발급처 바로가기] [발급일 직접 입력] → [파일 업로드]
 *            발급일 입력을 받는 서류는 날짜를 다 적어야 파일을 고를 수 있다 (2차 검증의 기준값)
 *   업로드 즉시 확인 안내 + 해결 방법 + 재업로드 (R2.1·R2.2)
 */

import { useEffect, useRef, useState } from 'react'

import {
  deleteDocument,
  fetchChecklist,
  fetchInterviewFormFileOptions,
  putDocContext,
  uploadDocument,
  type Checklist,
  type DocContext,
  type DocRequirementRow,
  type UploadedDocument,
} from '../../api.ts'
import FilePreview from '../../components/FilePreview.tsx'
import Modal from '../../components/Modal.tsx'
import PdfPages from '../../components/PdfPages.tsx'
import StatusBadge from '../../components/StatusBadge.tsx'
import { DateTriple } from '../../forms/FormSheet.tsx'
import { EMPTY_YMD, isCompleteYMD, ymdToISO, type YMD } from '../../forms/ymd.ts'
import './document-upload.css'

const WORKPLACE_COUNTS = ['1개', '2개', '3개'] as const

/** 판독 계층·신뢰도·소요시간은 신청자에게 의미가 없다. 시연에서 보여줄 때만 `?debug=1`. */
const SHOW_TECH = new URLSearchParams(window.location.search).has('debug')

/**
 * 판정 도장. 서류 접수 때 찍는 도장처럼 결과를 한 번에 보여준다.
 * 슬롯 머리 오른쪽에 하나만 둔다 — 상태를 여러 곳에서 반복하지 않는다.
 */
/** 파일 형식 표시 (PDF·JPG·PNG). */
function fileKind(name: string): string {
  return (name.split('.').pop() ?? '').toUpperCase().slice(0, 4) || 'FILE'
}

function isPdf(doc: UploadedDocument): boolean {
  return (doc.file_format || doc.file_name).toLowerCase().endsWith('pdf')
}

function DocumentThumbnail({ doc, onClick }: { doc: UploadedDocument; onClick: () => void }) {
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const pdf = isPdf(doc)
  const extension = fileKind(doc.file_name)
  const kind = extension === 'JPEG' ? 'JPG' : extension

  return (
    <button
      type="button"
      className="dresult__kind"
      onClick={onClick}
      aria-label={`${doc.file_name} 크게 보기`}
    >
      {!failed && (pdf ? (
        <PdfPages
          url={doc.file_url}
          width={56}
          maxHeight={76}
          maxPages={1}
          className={ready ? 'dresult__pages dresult__pages--ready' : 'dresult__pages'}
          onReady={() => setReady(true)}
          onError={() => setFailed(true)}
        />
      ) : (
        <img
          className="dresult__image"
          src={doc.file_url}
          alt=""
          onLoad={() => setReady(true)}
          onError={() => setFailed(true)}
        />
      ))}
      {(!ready || failed) && <span className="dresult__fallback">{kind}</span>}
      {ready && !failed && <span className="dresult__badge">{kind}</span>}
    </button>
  )
}

function DocumentResult({
  doc,
  onRetry,
}: {
  doc: UploadedDocument
  onRetry: () => void
}) {
  const [viewing, setViewing] = useState(false)
  const status = doc.status ?? 'NEEDS_REVIEW'
  const extracted = Object.entries(doc.extracted)
  return (
    <div className={`dresult dresult--${status.toLowerCase()}`}>
      <div className="dresult__file">
        <DocumentThumbnail key={doc.file_url} doc={doc} onClick={() => setViewing(true)} />
        <div className="dresult__body">
          <button type="button" className="dresult__name" onClick={() => setViewing(true)}>
            {doc.file_name}
          </button>
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
          {/* 확인이 필요한 경우에만 판독된 서류 종류를 함께 보여준다 */}
          {status !== 'PASS' && doc.detected_doc_type && (
            <span className="dresult__detected">읽은 서류 종류: {doc.detected_doc_type}</span>
          )}
          {SHOW_TECH && (
            <span className="dresult__meta">
              신뢰도 {doc.ocr_confidence?.toFixed(2) ?? '-'} / {doc.elapsed_ms ?? 0}ms
            </span>
          )}
        </div>
        <div className="dresult__actions">
          <button type="button" className="btn btn--small" onClick={() => setViewing(true)}>
            미리보기
          </button>
          <button type="button" className="btn btn--small dresult__retry" onClick={onRetry}>
            다시 올리기
          </button>
        </div>
      </div>
      {viewing && (
        <FilePreview
          url={doc.file_url}
          name={doc.file_name}
          kind={(doc.file_format || doc.file_name).toLowerCase().endsWith('pdf') ? 'pdf' : 'image'}
          onClose={() => setViewing(false)}
        />
      )}

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
  applicationId,
  busy,
  declared,
  onDeclaredChange,
  onPick,
  onRetry,
}: {
  item: DocRequirementRow
  applicationId: number
  busy: boolean
  declared: YMD
  onDeclaredChange: (v: YMD) => void
  onPick: (file: File) => void
  onRetry: (doc: UploadedDocument) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [infoOpen, setInfoOpen] = useState(false)
  const [interviewFormOpen, setInterviewFormOpen] = useState(false)
  const [interviewPdfReady, setInterviewPdfReady] = useState(false)
  const [interviewHwp, setInterviewHwp] = useState<string | null>(null)
  const doc = item.documents[0]
  const status = doc?.status ?? null
  // 발급일 직접 입력이 있는 서류는 날짜를 먼저 받아야 업로드 즉시 2차 검증을 할 수 있다.
  const dateReady = !item.check_declared_date || isCompleteYMD(declared)
  const issueISO = isCompleteYMD(declared) ? ymdToISO(declared) : ''
  const current = new Date()
  const todayISO = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}-${String(current.getDate()).padStart(2, '0')}`
  const basisLabel = item.date_basis_label || '발급일'
  const dateWarning = issueISO && issueISO > todayISO
    ? `${basisLabel}이 오늘 이후입니다. 다시 확인해 주세요.`
    : issueISO && item.min_issue_date && issueISO < item.min_issue_date
      ? `이 사업은 ${item.min_issue_date.replaceAll('-', '.')} 이후 ${basisLabel}만 인정합니다. 서류를 확인해 주세요.`
      : ''

  useEffect(() => {
    if (!/^(interview|suit)_\d+_confirmation$/.test(item.slot_key)) return
    let alive = true
    fetchInterviewFormFileOptions(applicationId).then((options) => {
      if (alive) setInterviewHwp(options.hwp)
    }).catch(() => { if (alive) setInterviewHwp(null) })
    return () => { alive = false }
  }, [applicationId, item.slot_key])

  return (
    <li
      className={`dslot dslot--${status ? status.toLowerCase() : 'empty'}`}
      id={`slot-${item.slot_key}`}
    >
      <div className="dslot__head">
        <div className="dslot__title">
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
        </div>
        {status ? (
          <StatusBadge status={status} audience="applicant" />
        ) : (
          item.issuer_url && (
            <a className="dslot__issuer" href={item.issuer_url} target="_blank" rel="noreferrer">
              {item.issuer}에서 발급받기 ↗
            </a>
          )
        )}
      </div>

      <p className="dslot__criteria">{item.issue_rule_label}{item.notes.filter((note) => note.startsWith('조회기간에 ') || note.startsWith('최근 ')).map((note) => ` · ${note}`).join('')}</p>

      {/^(interview|suit)_\d+_confirmation$/.test(item.slot_key) && (
        <details className="dslot__files-menu"><summary className="btn btn--small">면접확인서 양식</summary>
          <a href={`/api/applications/${applicationId}/forms/files/job_interview_confirmation/blank.pdf`}>빈 서식 PDF</a>
          {interviewHwp && <a href={interviewHwp}>원본 HWP</a>}
          <button type="button" className="btn btn--small" onClick={() => { setInterviewPdfReady(false); setInterviewFormOpen(true) }}>미리보기</button>
        </details>
      )}

      {/* 올리기 전: 발급일 → 파일 업로드. 올린 뒤에는 결과만 남긴다. */}
      {!doc && (
        <div className="dslot__action">
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
              <span className="dslot__declared-label">서류에 적힌 {basisLabel}</span>
              <DateTriple value={declared} onChange={onDeclaredChange} ariaPrefix={item.label} />
            </label>
          )}
          {dateWarning && <p className="dslot__date-warning" role="status">{dateWarning}</p>}
          <button
            type="button"
            className="btn btn--primary dslot__upload"
            disabled={busy || !dateReady}
            onClick={() => input.current?.click()}
          >
            {busy ? '읽는 중…' : '파일 업로드'}
          </button>
          {!dateReady && !busy && (
            <p className="dslot__gate">{basisLabel}을 입력하면 파일을 올릴 수 있습니다.</p>
          )}
        </div>
      )}

      {doc && <DocumentResult doc={doc} onRetry={() => onRetry(doc)} />}
      {infoOpen && <SlotInfoModal item={item} onClose={() => setInfoOpen(false)} />}
      {interviewFormOpen && (
        <Modal
          title="면접확인서 양식 보기"
          onClose={() => setInterviewFormOpen(false)}
          variant="printable-viewer"
          footer={<button type="button" className="btn btn--primary" disabled={!interviewPdfReady} onClick={() => window.print()}>인쇄</button>}
        >
          <div className="dupload__form-preview">
            <p>신청자 정보가 미리 들어 있습니다. 회사에서 면접 내용과 확인 서명을 작성합니다.</p>
            <img
              className="dupload__form-page"
              src={`/api/applications/${applicationId}/forms/job_interview_confirmation/pages/1.png?preview=true`}
              alt="면접확인서 양식"
              onLoad={() => setInterviewPdfReady(true)}
              onError={() => setInterviewPdfReady(false)}
            />
          </div>
        </Modal>
      )}
    </li>
  )
}

export default function DocumentUpload({
  applicationId,
  onProgress,
}: {
  applicationId: number
  onProgress: (uploaded: number, total: number) => void
}) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [declared, setDeclared] = useState<Record<string, YMD>>({})
  const [busySlot, setBusySlot] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetchChecklist(applicationId)
      .then((next) => {
        setChecklist(next)
        onProgress(next.upload_done, next.upload_total)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [applicationId, onProgress])

  const context = checklist?.context ?? {}

  /** 근로유형 등이 바뀌면 서버가 다시 조립한 체크리스트로 통째로 갈아끼운다. */
  const changeContext = async (patch: Partial<DocContext>) => {
    const proofRows = checklist?.items.filter((item) =>
      item.slot_key.startsWith('work_proof') || item.slot_key === 'labor_contract'
    ) ?? []
    const changesWorkTypeOrCount = (['work_category', 'workplace_count'] as const)
      .some((key) => patch[key] !== undefined && patch[key] !== context[key])
    const changesAdminContract = patch.admin_fixed_term !== undefined &&
      patch.admin_fixed_term !== context.admin_fixed_term
    const proofDocs = proofRows
      .filter((item) => changesWorkTypeOrCount || (changesAdminContract && item.slot_key === 'labor_contract'))
      .flatMap((item) => item.documents)
    if (proofDocs.length > 0 &&
      !window.confirm('올리신 근로확인서류가 빠집니다. 바꾸시겠어요?')) return

    setError('')
    setBusySlot('work-context')
    try {
      if (proofDocs.length > 0) {
        for (const doc of proofDocs) await deleteDocument(applicationId, doc.document_id)
      }
      const next = await putDocContext(applicationId, { ...context, ...patch })
      setChecklist(next)
      onProgress(next.upload_done, next.upload_total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
      await refresh()
    } finally {
      setBusySlot('')
    }
  }

  const refresh = () => fetchChecklist(applicationId).then((next) => {
    setChecklist(next)
    onProgress(next.upload_done, next.upload_total)
  })

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
  const hasAdminConsent = checklist.items.some((i) => i.slot_key === 'admin_info_consent')

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
          <fieldset className="dupload__worktypes" disabled={busySlot === 'work-context'}>
            <legend>근로유형 선택</legend>
            {checklist.work_categories.map((category, index) => {
              const id = `work-category-${applicationId}-${index}`
              return (
                <label key={category} htmlFor={id}>
                  <input
                    id={id}
                    type="radio"
                    name={`work-category-${applicationId}`}
                    value={category}
                    checked={context.work_category === category}
                    onChange={() => void changeContext({ work_category: category })}
                  />
                  <span>{category}</span>
                </label>
              )
            })}
          </fieldset>
          <div className="dupload__opts">
            {context.work_category === '직장가입자' && (
              <label>
                <input
                  type="checkbox"
                  checked={!!context.admin_fixed_term}
                  disabled={busySlot === 'work-context'}
                  onChange={(e) => void changeContext({ admin_fixed_term: e.target.checked })}
                />
                행정기관 기간제 근로자입니다 (근로계약서 사본 추가)
              </label>
            )}
            <label>
              근무 사업장 수
              <select
                value={`${context.workplace_count ?? 1}개`}
                disabled={busySlot === 'work-context'}
                onChange={(e) => void changeContext({ workplace_count: Number(e.target.value[0]) })}
              >
                {WORKPLACE_COUNTS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
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
            applicationId={applicationId}
            busy={busySlot === item.slot_key}
            declared={declared[item.slot_key] ?? EMPTY_YMD}
            onDeclaredChange={(v) => setDeclared({ ...declared, [item.slot_key]: v })}
            onPick={(file) => void upload(item, file)}
            onRetry={(doc) => void retry(doc)}
          />
        ))}
      </ul>

      {(onlineItems.length > 0 || hasAdminConsent) && (
        <section className="dupload__online">
          <h3>업로드하지 않아도 되는 서류</h3>
          <ul>
            {onlineItems.filter((i) => i.slot_key !== 'admin_info_consent').map((i) => (
              <li key={i.slot_key}>
                <strong>{i.label}</strong> — {i.fulfilled_by}(으)로 대체되었습니다.
              </li>
            ))}
            {hasAdminConsent && (
              <li>
                <strong>행정정보 공동이용 사전동의서 (서식5)</strong>
                {' — '}{context.paper_forms?.['서식5'] ? '종이 작성 스캔본을 제출합니다.' : '온라인 작성 동의와 서명을 제출합니다.'}
              </li>
            )}
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
