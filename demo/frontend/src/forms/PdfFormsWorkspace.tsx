import { useEffect, useState } from 'react'

import {
  fetchFormLayout,
  fetchSubsidyItems,
  saveSubsidyItems,
  type FormFieldLayout,
  type FormLayout,
  type Identity,
  type Program,
  type SubsidySelection,
  type SelfCheckResult,
  type SubsidyState,
} from '../api.ts'
import Modal from '../components/Modal.tsx'
import PdfPages from '../components/PdfPages.tsx'
import SignaturePad from '../components/SignaturePad.tsx'
import type { ConsentValue } from './consent-model.ts'
import { EMPTY_FORM1, type Form1Value } from './form1-model.ts'
import { JOB_PACKAGE_SELF_CHECK_ITEMS, SELF_CHECK_ITEMS, type SelfCheckAnswers } from './form2-model.ts'
import { EMPTY_FORM5, type Form5Value, type SignMode } from './form5-model.ts'
import './pdf-forms-workspace.css'

const JOB_FORMS = ['job_application', 'job_consent']
const SAVINGS_FORMS = ['서식2', '서식1', '서식3', '서식4', '서식5']
type ActiveForm = { formNo: string; mode: 'edit' | 'preview' }

interface Props {
  applicationId: number
  program: Program
  identity: Identity | null
  form1: Form1Value
  answers: SelfCheckAnswers
  consent: ConsentValue
  form5: Form5Value
  signMode: SignMode
  checkResult: SelfCheckResult | null
  onForm1: (value: Form1Value) => void
  onAnswers: (value: SelfCheckAnswers) => void
  onConsent: (value: ConsentValue) => void
  onForm5: (value: Form5Value) => void
  onSignMode: (value: SignMode) => void
  onFlush: () => Promise<void>
  onChangedSubsidy?: (state: SubsidyState) => void
  onContinue: () => void
  continuing: boolean
  error: string
  readOnly?: boolean
}

function truthy(value: unknown): boolean {
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0
  if (value && typeof value === 'object' && 'y' in value) {
    const date = value as { y?: string; m?: string; d?: string }
    return !!(date.y && date.m && date.d)
  }
  return Boolean(value)
}

function dateText(value: unknown): string {
  if (!value || typeof value !== 'object' || !('y' in value)) return ''
  const date = value as { y?: string; m?: string; d?: string }
  return [date.y, date.m, date.d].filter(Boolean).join('. ')
}

function readForm(form1: Form1Value, key: string): unknown {
  return (form1 as unknown as Record<string, unknown>)[key]
}

function durationBand(value: Form1Value['transferIn'], basis: string, work: boolean): string {
  if (!value.y || !value.m || !value.d) return ''
  const start = new Date(Number(value.y), Number(value.m) - 1, Number(value.d))
  const end = new Date(`${basis}T00:00:00`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return ''
  let years = end.getFullYear() - start.getFullYear()
  if (end.getMonth() < start.getMonth() || (end.getMonth() === start.getMonth() && end.getDate() < start.getDate())) years -= 1
  if (work) return years >= 3 ? '3년 이상' : `${years}년 이상 ~ ${years + 1}년 미만`
  return years >= 5 ? '5년 이상' : `${years}년 이상 ~ ${years + 1}년 미만`
}

function requiredKeys(formNo: string, isJob: boolean): string[] {
  if (formNo === '서식2') return Array.from({ length: 8 }, (_, i) => `self_check.${i + 1}`)
  if (formNo === '서식1') return [
    'name', 'birth', 'address', 'mobile', 'email', 'savingPurpose', 'priorJoined',
    'gender', 'householdType', 'householdSize', 'workType', 'workplaceRegion',
    'bankName', 'accountNo', 'accountHolder',
  ]
  if (formNo === '서식3') return ['consent.privacy', 'consent.uniqueId']
  if (formNo === '서식4') return ['consent.thirdParty']
  if (formNo === '서식5') return ['agree', 'signature']
  if (formNo === 'job_application') return [
    'name', 'birth', 'address', 'mobile', 'email', 'bankName', 'accountNo', 'job.signature',
  ]
  if (formNo === 'job_consent') return ['consent.privacy', 'consent.thirdParty', 'consent.job.signature']
  return isJob ? ['self_check.1', 'self_check.2'] : []
}

function fieldGroup(key: string): string {
  if (key.startsWith('self_check.')) return key.split('.').slice(0, 2).join('.')
  if (key.startsWith('consent.')) return key.split('.').slice(0, 2).join('.')
  if (key.startsWith('agree.')) return 'agree'
  if (key.startsWith('subsidy.')) return key.split('.').slice(0, 2).join('.')
  return key.split('.')[0]
}

export default function PdfFormsWorkspace({
  applicationId, program, identity, form1, answers, consent, form5, signMode,
  checkResult, onForm1, onAnswers, onConsent, onForm5, onSignMode,
  onFlush, onChangedSubsidy, onContinue, continuing, error, readOnly = false,
}: Props) {
  const isJob = program.has_subsidy_items
  const formNos = isJob ? JOB_FORMS : SAVINGS_FORMS
  const [layouts, setLayouts] = useState<Record<string, FormLayout>>({})
  const [active, setActive] = useState<ActiveForm | null>(null)
  const [page, setPage] = useState(0)
  const [localError, setLocalError] = useState('')
  const [saving, setSaving] = useState(false)
  const [signatureTarget, setSignatureTarget] = useState<string | null>(null)
  const [previewKey, setPreviewKey] = useState(0)
  const [selectedItems, setSelectedItems] = useState<string[]>([])
  const [subsidySelections, setSubsidySelections] = useState<SubsidySelection[]>([])
  const selfCheckItems = isJob ? JOB_PACKAGE_SELF_CHECK_ITEMS : SELF_CHECK_ITEMS

  useEffect(() => {
    let alive = true
    Promise.all(formNos.map((formNo) => fetchFormLayout(applicationId, formNo)))
      .then((items) => {
        if (alive) setLayouts(Object.fromEntries(items.map((item) => [item.form_no, item])))
      })
      .catch((e: unknown) => {
        if (alive) setLocalError(e instanceof Error ? e.message : String(e))
      })
    if (isJob) {
      fetchSubsidyItems(applicationId).then((state) => {
        setSelectedItems(state.selections.map((item) => item.item_type))
        setSubsidySelections(state.selections)
      }).catch(() => undefined)
    }
    return () => { alive = false }
  }, [applicationId, formNos, isJob])

  const currentLayout = active ? layouts[active.formNo] : undefined
  const pageSize = currentLayout?.page_sizes[page]
  const pageWidth = 794
  const scale = pageSize ? pageWidth / pageSize.width : 1

  const readChoice = (key: string): boolean => {
    const [group, option] = [fieldGroup(key), key.split('.').slice(-1)[0]]
    if (group.startsWith('self_check.')) return answers[Number(group.split('.')[1])] === option
    if (group === 'consent.privacy') return consent.privacy === option
    if (group === 'consent.uniqueId') return consent.uniqueId === option
    if (group === 'consent.thirdParty') return consent.thirdParty === option
    if (group === 'agree') return form5.agree === option
    if (group.startsWith('subsidy.')) return selectedItems.includes(group.split('.')[1])
    if (group === 'referralPaths') return form1.referralPaths.some((item) => item.startsWith(option))
    if (group === 'residencePeriod') return durationBand(form1.transferIn, program.announcement_date, false) === option
    if (group === 'workPeriod') return durationBand(form1.employedAt, program.announcement_date, true) === option
    return readForm(form1, group) === option
  }

  const readText = (key: string): string => {
    if (key === 'birth') return dateText(form1.birth)
    if (key === 'name' && identity) return identity.name
    if (key === 'phone') return form5.phone || form1.mobile
    if (key === 'writtenMonth') return String(new Date().getMonth() + 1)
    if (key === 'writtenDay') return String(new Date().getDate())
    if (key.startsWith('consent.form') || key.startsWith('consent.job.') && !key.endsWith('signature')) {
      const date = new Date()
      if (key.endsWith('.year')) return String(date.getFullYear())
      if (key.endsWith('.month')) return String(date.getMonth() + 1)
      if (key.endsWith('.day')) return String(date.getDate())
    }
    if (key.startsWith('job.application')) {
      const date = new Date()
      if (key.endsWith('Year')) return String(date.getFullYear())
      if (key.endsWith('Month')) return String(date.getMonth() + 1)
      if (key.endsWith('Day')) return String(date.getDate())
    }
    if (key.startsWith('consent.job.')) return ''
    const suitLink = key.match(/^job\.suit\.(\d+)\.(company|location|date)$/)
    if (suitLink && selectedItems.includes('interview')) {
      const selection = subsidySelections.find((item) => item.item_type === 'suit')
      const interviewTurn = selection?.linked_interview_indices[Number(suitLink[1]) - 1]
      if (interviewTurn) return String(readForm(form1, `job.interview.${interviewTurn}.${suitLink[2]}`) || '')
    }
    const value = readForm(form1, key)
    if (typeof value === 'string') return value
    if (key === 'birth') return dateText(value)
    return ''
  }

  const isSelected = (group: string): boolean => {
    if (group.startsWith('self_check.')) return !!answers[Number(group.split('.')[1])]
    if (group === 'consent.privacy') return !!consent.privacy
    if (group === 'consent.uniqueId') return !!consent.uniqueId
    if (group === 'consent.thirdParty') return !!consent.thirdParty
    if (group === 'agree') return !!form5.agree
    if (group.startsWith('subsidy.')) return selectedItems.includes(group.split('.')[1])
    if (group === 'referralPaths') return form1.referralPaths.length > 0
    return truthy(readForm(form1, group))
  }

  const missing = (formNo: string): string[] => {
    const keys = requiredKeys(formNo, isJob)
    if (formNo === '서식1' && form1.householdSize === '10인 이상') keys.push('householdSizeCount')
    return keys.filter((key) => {
    if (key.startsWith('self_check.')) return !answers[Number(key.split('.')[1])]
    if (key === 'consent.privacy') return !consent.privacy
    if (key === 'consent.uniqueId') return !consent.uniqueId
    if (key === 'consent.thirdParty') return !consent.thirdParty
    if (key === 'agree') return !form5.agree
    if (key === 'signature') return signMode === '전자서명' ? !form5.signature : !form5.handwrittenFileName
    if (key === 'consent.job.signature') return !readForm(form1, key)
    return !truthy(readForm(form1, key))
    })
  }

  const allReady = formNos.every((formNo) => !!layouts[formNo] && missing(formNo).length === 0) &&
    (isJob ? selfCheckItems.every((item) => !!answers[item.no]) : true)

  const setText = (key: string, value: string) => {
    if (key === 'name' && identity) return
    if (key === 'birth' && identity) return
    if (key === 'consent.privacy') { onConsent({ ...consent, privacy: value }); return }
    if (key === 'consent.uniqueId') { onConsent({ ...consent, uniqueId: value }); return }
    if (key === 'consent.thirdParty') { onConsent({ ...consent, thirdParty: value }); return }
    if (key === 'agree') { onForm5({ ...form5, agree: value }); return }
    if (key === 'householdSizeCount') value = value.replace(/\D/g, '').slice(0, 2)
    if (key === 'birth' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const [y, m, d] = value.split('-')
      onForm1({ ...form1, birth: { y, m: String(Number(m)), d: String(Number(d)) } })
      return
    }
    onForm1({ ...(form1 as unknown as Record<string, unknown>), [key]: value } as unknown as Form1Value)
  }

  const toggleChoice = (key: string, checked: boolean) => {
    const group = fieldGroup(key)
    const option = key.split('.').slice(-1)[0]
    if (group.startsWith('self_check.')) {
      const no = group.split('.')[1]
      const answer = option as '예' | '아니오'
      onAnswers({ ...answers, [Number(no)]: checked ? answer : undefined })
      return
    }
    if (group === 'consent.privacy') { onConsent({ ...consent, privacy: checked ? option : '' }); return }
    if (group === 'consent.uniqueId') { onConsent({ ...consent, uniqueId: checked ? option : '' }); return }
    if (group === 'consent.thirdParty') { onConsent({ ...consent, thirdParty: checked ? option : '' }); return }
    if (group === 'agree') { onForm5({ ...form5, agree: checked ? option : '' }); return }
    if (group.startsWith('subsidy.')) {
      const itemType = group.split('.')[1]
      void (async () => {
        const state = await fetchSubsidyItems(applicationId)
        const selections = state.selections.filter((item) => item.item_type !== itemType)
        if (checked) selections.push({ item_type: itemType, count: 1, receipts: [null], linked_interview_indices: [1] })
        const saved = await saveSubsidyItems(applicationId, selections)
        setSelectedItems(saved.selections.map((item) => item.item_type))
        setSubsidySelections(saved.selections)
        onChangedSubsidy?.(saved)
      })().catch((e: unknown) => setLocalError(e instanceof Error ? e.message : String(e)))
      return
    }
    if (group === 'residencePeriod' || group === 'workPeriod') return
    if (group === 'referralPaths') {
      const old = form1.referralPaths
      const value = checked ? [...old, option] : old.filter((item) => !item.startsWith(option))
      onForm1({ ...form1, referralPaths: value })
      return
    }
    const value = readForm(form1, group)
    onForm1({ ...(form1 as unknown as Record<string, unknown>), [group]: checked ? option : value === option ? '' : value } as unknown as Form1Value)
  }

  const setSignature = (formNo: string, value: string) => {
    if (formNo === '서식5') {
      onForm5({ ...form5, signature: value })
      return
    }
    const storeKey = formNo === 'job_consent' ? 'consent.job.signature' : 'job.signature'
    onForm1({ ...(form1 as unknown as Record<string, unknown>), [storeKey]: value } as unknown as Form1Value)
  }

  const signatureValue = (formNo: string): string => {
    if (formNo === '서식5') return form5.signature
    const key = formNo === 'job_consent' ? 'consent.job.signature' : 'job.signature'
    const value = readForm(form1, key)
    return typeof value === 'string' ? value : ''
  }

  const resetForm = (formNo: string) => {
    if (!window.confirm('이 서식의 작성값과 서명을 모두 비울까요?')) return
    if (formNo === '서식2') onAnswers({})
    else if (formNo === '서식3') onConsent({ ...consent, privacy: '', uniqueId: '' })
    else if (formNo === '서식4') onConsent({ ...consent, thirdParty: '' })
    else if (formNo === '서식5') { onForm5(EMPTY_FORM5); onSignMode('전자서명') }
    else if (formNo === 'job_consent') {
      onConsent({ ...consent, privacy: '', thirdParty: '' })
      onForm1({ ...(form1 as unknown as Record<string, unknown>), 'consent.job.signature': '' } as unknown as Form1Value)
    } else {
      const reset = { ...EMPTY_FORM1 }
      if (identity) {
        reset.name = identity.name
        const [y, m, d] = identity.birth.split('-')
        reset.birth = { y, m: String(Number(m)), d: String(Number(d)) }
      }
      onForm1(reset)
    }
  }

  const startPreview = async (formNo: string) => {
    setSaving(true)
    setLocalError('')
    try {
      if (!readOnly) await onFlush()
      setPreviewKey((key) => key + 1)
      setPage(0)
      setActive({ formNo, mode: 'preview' })
    } catch (e: unknown) {
      setLocalError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const submitWorkspace = () => {
    if (readOnly) return
    if (!allReady) {
      setLocalError('필수 칸과 자가진단 문항을 모두 작성해 주세요.')
      return
    }
    onContinue()
  }

  const templateUrl = active ? `/api/applications/${applicationId}/forms/templates/${encodeURIComponent(active.formNo)}.pdf` : ''
  const previewUrl = active ? `/api/applications/${applicationId}/forms/${encodeURIComponent(active.formNo)}.pdf?v=${previewKey}` : ''

  const renderField = ([key, field]: [string, FormFieldLayout]) => {
    if (!active || field.page !== page) return null
    const [x0, y0, x1, y1] = field.box
    const boxStyle = {
      left: x0 * scale,
      top: y0 * scale,
      width: Math.max(8, (x1 - x0) * scale),
      height: Math.max(8, (y1 - y0) * scale),
    }
    const isMissing = missing(active.formNo).some((required) => required === key || fieldGroup(key) === required)
    const label = field.anchor || field.label || key
    if (field.type === 'check') {
      const checked = readChoice(key)
      const derived = fieldGroup(key) === 'residencePeriod' || fieldGroup(key) === 'workPeriod'
      return (
        <label key={key} className={`pdf-form__check ${isMissing && !isSelected(fieldGroup(key)) ? 'is-missing' : ''}`} style={boxStyle}>
          <input
            id={`pdf-field-${active.formNo}-${key}`}
            type="checkbox"
            checked={checked}
            disabled={derived || readOnly}
            aria-label={`${label} ${field.label || key.split('.').slice(-1)[0]}`}
            onChange={(event) => toggleChoice(key, event.currentTarget.checked)}
          />
        </label>
      )
    }
    if (field.type === 'image') {
      const value = signatureValue(active.formNo)
      return (
        <button
          key={key}
          type="button"
          id={`pdf-field-${active.formNo}-${key}`}
          disabled={readOnly}
          className={`pdf-form__sign ${isMissing && !value ? 'is-missing' : ''}`}
          style={boxStyle}
          aria-label="서명 입력란"
          onClick={() => setSignatureTarget(key)}
        >
          {value ? <img src={value} alt="입력한 서명" /> : <span>서명</span>}
        </button>
      )
    }
    const value = readText(key)
    const required = requiredKeys(active.formNo, isJob).includes(key)
    const round = key.match(/^job\.(interview|suit|certificate)\.(\d+)\./)
    const roundEnabled = !round || (subsidySelections.find((item) => item.item_type === round[1])?.count ?? 0) >= Number(round[2])
    const photoEnabled = !key.startsWith('job.photo.') || selectedItems.includes('photo')
    const householdCountEnabled = key !== 'householdSizeCount' || form1.householdSize === '10인 이상'
    const suitField = key.match(/^job\.suit\.(\d+)\.(company|location|date)$/)
    const suitLink = suitField
      ? subsidySelections.find((item) => item.item_type === 'suit')?.linked_interview_indices[Number(suitField[1]) - 1]
      : null
    const suitFieldsLinked = !!suitField && selectedItems.includes('interview') && !!suitLink
    const locked = !!identity && (key === 'name' || key === 'birth')
    const dateValue = key === 'birth'
      ? (() => {
          const b = form1.birth
          if (!b.y || !b.m || !b.d) return ''
          return `${b.y}-${String(Number(b.m)).padStart(2, '0')}-${String(Number(b.d)).padStart(2, '0')}`
        })()
      : value
    const baseFont = Math.min(12, Math.max(8, Number(field.size || 9) * scale))
    const fitFont = value.length > 0 ? Math.max(7, Math.min(baseFont, boxStyle.width / (value.length * 0.62))) : baseFont
    return (
      <input
        key={key}
        id={`pdf-field-${active.formNo}-${key}`}
        type="text"
        className={`pdf-form__text ${isMissing && required ? 'is-missing' : ''}`}
        style={{ ...boxStyle, fontSize: fitFont, textAlign: field.align || 'left' }}
        aria-label={label}
        value={dateValue}
        readOnly={readOnly || locked || !roundEnabled || !photoEnabled || !householdCountEnabled || suitFieldsLinked || key.startsWith('written') || key.includes('.year') || key.includes('.month') || key.includes('.day') || key.startsWith('job.application')}
        inputMode={key === 'householdSizeCount' ? 'numeric' : undefined}
        onChange={(event) => setText(key, event.currentTarget.value)}
      />
    )
  }

  const formLabel = (formNo: string) => {
    const layout = layouts[formNo]
    return layout?.public_form ? `공고문 ${layout.public_form}` : layout?.title || formNo
  }

  const itemLabelForStatus = (formNo: string) => {
    if (!layouts[formNo]) return '불러오는 중'
    return missing(formNo).length === 0 ? '작성 완료' : truthyForm(formNo, form1, answers, consent, form5) ? '작성 중' : '미작성'
  }

  return (
    <section className="pdf-forms">
      <header className="pdf-forms__intro">
        <h2>신청 서식 작성</h2>
        <p>원본 서식 위에 직접 입력합니다. 작성 내용은 자동 저장됩니다.</p>
      </header>
      <ul className="pdf-forms__list">
        {formNos.map((formNo) => {
          const state = itemLabelForStatus(formNo)
          return (
            <li key={formNo} className={`pdf-form-row pdf-form-row--${state === '작성 완료' ? 'done' : state === '미작성' ? 'empty' : 'draft'}`}>
              <div className="pdf-form-row__info">
                <strong>{formLabel(formNo)}</strong>
                <span>{state}</span>
              </div>
              <div className="pdf-form-row__actions">
                {!readOnly && <button type="button" className="btn btn--primary" disabled={!layouts[formNo]} onClick={() => { setPage(0); setSignatureTarget(null); setActive({ formNo, mode: 'edit' }) }}>
                  {state === '작성 완료' ? '수정' : '작성하기'}
                </button>}
                <button type="button" className="btn" disabled={!layouts[formNo] || saving} onClick={() => void startPreview(formNo)}>미리보기</button>
                {!readOnly && <button type="button" className="btn" disabled={!layouts[formNo] || state === '미작성'} onClick={() => resetForm(formNo)}>처음부터 다시</button>}
              </div>
            </li>
          )
        })}
      </ul>

      {isJob && (
        <section className="pdf-forms__selfcheck">
          <h3>지원 자격 확인</h3>
          {selfCheckItems.map((item) => (
            <fieldset key={item.no}>
              <legend>{item.question}</legend>
              {(['예', '아니오'] as const).map((answer) => (
                <label key={answer}>
                  <input type="radio" disabled={readOnly} name={`job-selfcheck-${item.no}`} checked={answers[item.no] === answer} onChange={() => onAnswers({ ...answers, [item.no]: answer })} />
                  {answer}
                </label>
              ))}
            </fieldset>
          ))}
        </section>
      )}

      {checkResult && !checkResult.eligible && checkResult.failed_item && (
        <p className="pdf-forms__error" role="alert">{checkResult.failed_item}번 문항: {checkResult.reason}</p>
      )}
      {(localError || error) && <p className="pdf-forms__error" role="alert">{localError || error}</p>}
      <div className="flow__actions">
        <button type="button" className="btn" onClick={() => window.scrollTo({ top: 0 })}>서식 목록</button>
        {!readOnly && <button type="button" className="btn btn--primary" disabled={!allReady || continuing} onClick={submitWorkspace}>
          {continuing ? '저장 중…' : isJob ? '지원 항목 단계로' : '서류 업로드로'}
        </button>}
      </div>

      {active && currentLayout && (
        <Modal
          title={`${formLabel(active.formNo)} ${active.mode === 'preview' ? '미리보기' : '작성'}`}
          onClose={() => { setActive(null); setSignatureTarget(null) }}
          variant="viewer"
          footer={active.mode === 'edit' && !readOnly ? (
            <>
              <button type="button" className="btn" onClick={() => void startPreview(active.formNo)}>미리보기</button>
              <button type="button" className="btn" onClick={() => { setActive(null); setSignatureTarget(null) }}>저장하고 닫기</button>
            </>
          ) : active.mode === 'preview' && !readOnly ? (
            <button type="button" className="btn btn--primary" onClick={() => setActive({ ...active, mode: 'edit' })}>수정</button>
          ) : null}
        >
          <div className="pdf-form__toolbar">
            <button type="button" className="btn" disabled={page <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>◀</button>
            <span>{page + 1} / {currentLayout.page_sizes.length}쪽</span>
            <button type="button" className="btn" disabled={page >= currentLayout.page_sizes.length - 1} onClick={() => setPage((p) => Math.min(currentLayout.page_sizes.length - 1, p + 1))}>▶</button>
            {active.mode === 'edit' && <span className="pdf-form__hint">칸을 탭으로 이동할 수 있습니다.</span>}
          </div>
          <div className="pdf-form__scroll">
            {active.mode === 'preview' ? (
              <PdfPages url={previewUrl} width={pageWidth} pageNo={page + 1} />
            ) : (
              <div className="pdf-form__page" style={{ width: pageWidth, height: pageSize ? pageSize.height * scale : 'auto' }}>
                <PdfPages url={templateUrl} width={pageWidth} pageNo={page + 1} />
                <div className="pdf-form__overlay" style={{ width: pageWidth, height: pageSize ? pageSize.height * scale : 'auto' }}>
                  {Object.entries(currentLayout.fields)
                    .sort((a, b) => a[1].page - b[1].page || a[1].box[1] - b[1].box[1] || a[1].box[0] - b[1].box[0])
                    .map(renderField)}
                </div>
              </div>
            )}
          </div>
          {active.mode === 'edit' && !readOnly && active.formNo === '서식5' && (
            <div className="pdf-form__signature-mode">
              <strong>서명 방식</strong>
              <label><input type="radio" checked={signMode === '전자서명'} onChange={() => onSignMode('전자서명')} /> 전자서명</label>
              <label><input type="radio" checked={signMode === '자필 스캔본 업로드'} onChange={() => onSignMode('자필 스캔본 업로드')} /> 자필 스캔본 제출</label>
              <span>자필 서명본 제출은 업로드 단계에서 선택할 수 있습니다.</span>
            </div>
          )}
          {active.mode === 'edit' && !readOnly && signatureTarget && (
            <div className="pdf-form__sign-pad">
              <h4>서명 입력 <button type="button" className="btn" onClick={() => setSignatureTarget(null)}>닫기</button></h4>
              {active.formNo === '서식5' && signMode === '자필 스캔본 업로드' ? (
                <label>서명 스캔본 파일 이름
                  <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(event) => onForm5({ ...form5, handwrittenFileName: event.target.files?.[0]?.name || '' })} />
                </label>
              ) : (
                <>
                  <SignaturePad value={signatureValue(active.formNo)} onChange={(value) => setSignature(active.formNo, value)} width={260} height={90} />
                  <button type="button" className="btn" onClick={() => setSignature(active.formNo, '')}>서명 다시 하기</button>
                </>
              )}
            </div>
          )}
          {active.mode === 'edit' && !readOnly && active.formNo === '서식1' && (
            <div className="pdf-form__extra">
              <strong>기간 산정에 쓰는 날짜</strong>
              <label>전북 최종 전입일
                <input type="date" value={isoDate(form1.transferIn)} onChange={(event) => onForm1({ ...form1, transferIn: fromISO(event.currentTarget.value) })} />
              </label>
              <label>현 직장 입사일
                <input type="date" value={isoDate(form1.employedAt)} onChange={(event) => onForm1({ ...form1, employedAt: fromISO(event.currentTarget.value) })} />
              </label>
              <span>기간 구간은 공고일 기준으로 서식에 자동 표시됩니다.</span>
            </div>
          )}
          {active.mode === 'edit' && !readOnly && missing(active.formNo).length > 0 && (
            <div className="pdf-form__missing">
              <strong>빠진 항목</strong>
              <ul>{missing(active.formNo).map((key) => (
                <li key={key}><button type="button" onClick={() => {
                  const entry = Object.entries(currentLayout.fields).find(([fieldKey]) => fieldKey === key || fieldGroup(fieldKey) === key)
                  const fieldKey = entry?.[0] || key
                  const field = entry?.[1]
                  if (field) setPage(field.page)
                  requestAnimationFrame(() => document.getElementById(`pdf-field-${active.formNo}-${fieldKey}`)?.focus())
                }}>{key}</button></li>
              ))}</ul>
            </div>
          )}
        </Modal>
      )}
    </section>
  )
}

function isoDate(value: Form1Value['transferIn']): string {
  if (!value.y || !value.m || !value.d) return ''
  return `${value.y}-${String(Number(value.m)).padStart(2, '0')}-${String(Number(value.d)).padStart(2, '0')}`
}

function fromISO(value: string): Form1Value['transferIn'] {
  if (!value) return { y: '', m: '', d: '' }
  const [y, m, d] = value.split('-')
  return { y, m: String(Number(m)), d: String(Number(d)) }
}

function truthyForm(formNo: string, form1: Form1Value, answers: SelfCheckAnswers, consent: ConsentValue, form5: Form5Value): boolean {
  if (formNo === '서식2') return Object.keys(answers).length > 0
  if (formNo === '서식3') return !!(consent.privacy || consent.uniqueId)
  if (formNo === '서식4') return !!consent.thirdParty
  if (formNo === '서식5') return !!(form5.agree || form5.signature || form5.handwrittenFileName)
  if (formNo === 'job_consent') return !!(consent.privacy || consent.thirdParty)
  return Object.values(form1).some(truthy)
}
