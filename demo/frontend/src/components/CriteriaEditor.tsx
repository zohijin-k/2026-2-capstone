import { useEffect, useState } from 'react'

import {
  fetchOfficerCriteria,
  saveOfficerCriteria,
  type CriteriaData,
  type CriteriaVersion,
  type IssueRule,
} from '../api.ts'

const DOCS: Record<string, { key: string; label: string }[]> = {
  double_savings: [
    { key: 'resident_abstract', label: '주민등록표 초본' },
    { key: 'nhis_payment', label: '건강보험료 납부확인서' },
    { key: 'nhis_qualification', label: '건강보험 자격확인서' },
    { key: 'nhis_acquisition_loss', label: '건강보험 자격득실확인서' },
    { key: 'work_proof', label: '근로확인서류' },
  ],
  job_package: [
    { key: 'resident_abstract', label: '주민등록표 초본' },
    { key: 'confirmation', label: '면접확인서' },
    { key: 'receipt', label: '결제 영수증' },
    { key: 'photo', label: '면접용 사진사본' },
    { key: 'exam', label: '시험 응시·성적 확인서' },
  ],
}

const MODES: { value: IssueRule['mode']; label: string }[] = [
  { value: 'after_date', label: '지정 날짜 이후 발급' },
  { value: 'after_notice', label: '공고일 이후 발급' },
  { value: 'within_days', label: '신청일 기준 N일 이내 발급' },
  { value: 'none', label: '발급일 기준 없음' },
]

const init = (data: CriteriaData) => ({
  announcement_date: data.announcement_date,
  application_period: [data.application_period[0] ?? '', data.application_period[1] ?? ''],
  application_period_2: data.application_period_2 ? [data.application_period_2[0] ?? '', data.application_period_2[1] ?? ''] : null,
  document_issue_rules: data.document_issue_rules,
  document_issue_fallback: data.document_issue_fallback,
  nhis_payment_months: data.nhis_payment_months,
  nhis_acquisition_loss_years: data.nhis_acquisition_loss_years,
})

export default function CriteriaEditor({
  code,
  onClose,
  applicantDemo = false,
}: {
  code: string
  onClose?: () => void
  applicantDemo?: boolean
}) {
  const [current, setCurrent] = useState<CriteriaData | null>(null)
  const [history, setHistory] = useState<CriteriaVersion[]>([])
  const [form, setForm] = useState<ReturnType<typeof init> | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetchOfficerCriteria(code)
      .then((data) => {
        setCurrent(data.current)
        setHistory(data.history)
        setForm(init(data.current))
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [code])

  if (error) return <p role="alert">{error}</p>
  if (!form || !current) return <p>심사 기준을 불러오는 중…</p>

  const changeRule = (key: string, rule: IssueRule) =>
    setForm((prev) => prev && ({ ...prev, document_issue_rules: { ...prev.document_issue_rules, [key]: rule } }))

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      const saved = await saveOfficerCriteria(code, 'province', form)
      setCurrent(saved)
      setHistory((prev) => [saved, ...prev])
      setForm(init(saved))
      setMessage(`기준 v${saved.version} 저장됨, 이후 새로 만드는 신청서부터 적용`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const monthValue = form.nhis_payment_months.join(', ')
  const monthChange = (value: string) => setForm((prev) => prev && ({
    ...prev,
    nhis_payment_months: value.split(',').map((s) => s.trim()).filter(Boolean),
  }))

  return (
    <section className="criteria-editor" aria-label="심사 기준 설정">
      <header className="criteria-editor__head">
        <div>
          <h2>{applicantDemo ? '관리자 설정 — 실서비스에서는 담당자 화면에서만 바뀝니다' : '심사 기준'}</h2>
          <p>현재 적용 기준 v{current.version}</p>
        </div>
        {onClose && <button type="button" onClick={onClose}>닫기</button>}
      </header>

      <fieldset disabled={busy}>
        <legend>공통 기준</legend>
        <label>공고일 <input type="date" value={form.announcement_date} onChange={(e) => setForm({ ...form, announcement_date: e.target.value })} /></label>
        <label>신청 시작일 <input type="date" value={form.application_period[0]} onChange={(e) => setForm({ ...form, application_period: [e.target.value, form.application_period[1]] })} /></label>
        <label>신청 종료일 <input type="date" value={form.application_period[1]} onChange={(e) => setForm({ ...form, application_period: [form.application_period[0], e.target.value] })} /></label>
        {form.application_period_2 && <>
          <label>2차 신청 시작일 <input type="date" value={form.application_period_2[0]} onChange={(e) => setForm({ ...form, application_period_2: [e.target.value, form.application_period_2![1]] })} /></label>
          <label>2차 신청 종료일 <input type="date" value={form.application_period_2[1]} onChange={(e) => setForm({ ...form, application_period_2: [form.application_period_2![0], e.target.value] })} /></label>
        </>}
      </fieldset>

      <table className="criteria-editor__table">
        <thead><tr><th>필수 서류</th><th>발급일 기준</th><th>값</th></tr></thead>
        <tbody>{(DOCS[code] ?? DOCS.double_savings).map((doc) => {
          const rule = form.document_issue_rules[doc.key] ?? form.document_issue_fallback
          return <tr key={doc.key}>
            <th scope="row">{doc.label}</th>
            <td><select value={rule.mode} onChange={(e) => {
              const mode = e.target.value as IssueRule['mode']
              changeRule(doc.key, { ...rule, mode, ...(mode === 'within_days' ? { days: rule.days ?? 30 } : {}) })
            }}>
              {MODES.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
            </select></td>
            <td>{rule.mode === 'after_date' ? <input type="date" value={rule.date ?? ''} onChange={(e) => changeRule(doc.key, { ...rule, date: e.target.value })} /> : null}
              {rule.mode === 'within_days' ? <input type="number" min={1} max={3650} value={rule.days ?? 30} onChange={(e) => changeRule(doc.key, { ...rule, days: Number(e.target.value) })} /> : null}
              {rule.mode === 'after_notice' ? `공고일 ${form.announcement_date}` : null}
              {rule.mode === 'none' ? '적용 안 함' : null}</td>
          </tr>
        })}</tbody>
      </table>

      <fieldset disabled={busy}>
        <legend>서류별 내용 기준</legend>
        <label>납부확인서 평균 고지월 (쉼표로 구분)
          <input value={monthValue} onChange={(e) => monthChange(e.target.value)} placeholder="2025-10, 2025-11, 2025-12" />
        </label>
        <label>자격득실확인서 변동내역 포함 기간 (년)
          <input type="number" min={1} max={10} value={form.nhis_acquisition_loss_years} onChange={(e) => setForm({ ...form, nhis_acquisition_loss_years: Number(e.target.value) })} />
        </label>
      </fieldset>

      <button type="button" disabled={busy} onClick={() => void save()}>{busy ? '저장 중…' : '기준 저장'}</button>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {!applicantDemo && <table className="criteria-editor__history"><caption>기준 버전 이력</caption><thead><tr><th>버전</th><th>저장 시각</th><th>역할</th></tr></thead><tbody>
        {history.map((item) => <tr key={item.version}><td>v{item.version}</td><td>{item.changed_at ?? '-'}</td><td>{item.changed_role ?? '-'}</td></tr>)}
      </tbody></table>}
    </section>
  )
}
