import { useEffect, useState } from 'react'

import {
  fetchOfficerCriteria,
  saveOfficerCriteria,
  type CriteriaData,
  type CriteriaSubsidyItem,
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
    { key: 'application_form', label: '신청서 및 동의서' },
    { key: 'resident_abstract', label: '주민등록표 초본' },
    { key: 'bank_account', label: '본인 명의 통장 사본' },
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
  document_date_bases: data.document_date_bases,
  nhis_payment_months: data.nhis_payment_months,
  nhis_acquisition_loss_years: data.nhis_acquisition_loss_years,
  supplement: data.supplement,
  subsidy_catalog: data.subsidy_catalog,
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
  const [monthYear, setMonthYear] = useState(2025)

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

  const changeCatalogItem = (itemType: string, change: Partial<CriteriaSubsidyItem>) =>
    setForm((prev) => prev && ({
      ...prev,
      subsidy_catalog: prev.subsidy_catalog.map((item) => item.item_type === itemType ? { ...item, ...change } : item),
    }))

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

  const toggleMonth = (month: number) => {
    const value = `${monthYear}-${String(month).padStart(2, '0')}`
    setForm((prev) => {
      if (!prev) return prev
      const selected = new Set(prev.nhis_payment_months)
      if (selected.has(value)) selected.delete(value)
      else selected.add(value)
      return { ...prev, nhis_payment_months: [...selected].sort() }
    })
  }

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
        <thead><tr><th>필수 서류</th><th>날짜 종류</th><th>기준</th><th>값</th></tr></thead>
        <tbody>{(DOCS[code] ?? DOCS.double_savings).map((doc) => {
          const rule = form.document_issue_rules[doc.key] ?? form.document_issue_fallback
          const basis = form.document_date_bases[doc.key] ?? 'issue_date'
          return <tr key={doc.key}>
            <th scope="row">{doc.label}</th>
            <td><select aria-label={`${doc.label} 기준 날짜 종류`} value={basis} onChange={(e) => setForm({ ...form, document_date_bases: { ...form.document_date_bases, [doc.key]: e.target.value as typeof basis } })}>
              <option value="issue_date">발급일</option><option value="payment_date">결제일</option>
              <option value="interview_date">면접일</option><option value="exam_date">응시일</option><option value="none">없음</option>
            </select></td>
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

      {code === 'job_package' && <fieldset disabled={busy}>
        <legend>취업패키지 지원 항목 기준</legend>
        <table className="criteria-editor__table">
          <thead><tr><th>지원 항목·안내</th><th>회당 한도</th><th>지급 방식</th><th>횟수</th><th>횟수 범위</th><th>필요 서류 · 기준 날짜</th></tr></thead>
          <tbody>{form.subsidy_catalog.map((item) => <tr key={item.item_type}>
            <th scope="row"><input aria-label={`${item.label} 항목 이름`} value={item.label} onChange={(e) => changeCatalogItem(item.item_type, { label: e.target.value })} />
              <textarea aria-label={`${item.label} 설명`} value={item.description} onChange={(e) => changeCatalogItem(item.item_type, { description: e.target.value })} />
              <textarea aria-label={`${item.label} 안내`} value={item.note} onChange={(e) => changeCatalogItem(item.item_type, { note: e.target.value })} />
            </th>
            <td><input aria-label={`${item.label} 회당 한도`} type="number" min={1} value={item.unit_cap} onChange={(e) => changeCatalogItem(item.item_type, { unit_cap: Number(e.target.value) })} />원</td>
            <td><select aria-label={`${item.label} 지급 방식`} value={item.actual_cost ? 'actual' : 'fixed'} onChange={(e) => changeCatalogItem(item.item_type, { actual_cost: e.target.value === 'actual' })}><option value="fixed">정액</option><option value="actual">실비</option></select></td>
            <td><input aria-label={`${item.label} 최대 횟수`} type="number" min={1} max={20} value={item.max_count} onChange={(e) => changeCatalogItem(item.item_type, { max_count: Number(e.target.value) })} />회</td>
            <td><select aria-label={`${item.label} 횟수 범위`} value={item.count_scope} onChange={(e) => changeCatalogItem(item.item_type, { count_scope: e.target.value as CriteriaSubsidyItem['count_scope'] })}><option value="application">신청서</option><option value="year">연간</option><option value="lifetime">생애</option></select></td>
            <td>{item.extra_docs.map((doc, index) => <label key={doc.suffix} className="criteria-editor__subsidy-doc">
              <input aria-label={`${item.label} 필요 서류 이름`} value={doc.label} onChange={(e) => {
                const extra_docs = item.extra_docs.map((entry, i) => i === index ? { ...entry, label: e.target.value } : entry)
                changeCatalogItem(item.item_type, { extra_docs })
              }} />
              <select aria-label={`${item.label} ${doc.label} 기준 날짜`} value={doc.date_basis} onChange={(e) => {
                const extra_docs = item.extra_docs.map((entry, i) => i === index ? { ...entry, date_basis: e.target.value as typeof entry.date_basis } : entry)
                changeCatalogItem(item.item_type, { extra_docs })
              }}>
                <option value="issue_date">발급일</option><option value="payment_date">결제일</option>
                <option value="interview_date">면접일</option><option value="exam_date">응시일</option><option value="none">없음</option>
              </select>
            </label>)}</td>
          </tr>)}</tbody>
        </table>
      </fieldset>}

      <fieldset disabled={busy}>
        <legend>서류별 내용 기준</legend>
        <div className="criteria-editor__month-picker">
          <strong>납부확인서 평균 고지월</strong>
          <div className="criteria-editor__month-year">
            <button type="button" onClick={() => setMonthYear((year) => year - 1)}>◀</button>
            <span>{monthYear}</span>
            <button type="button" onClick={() => setMonthYear((year) => year + 1)}>▶</button>
          </div>
          <div className="criteria-editor__month-grid" role="group" aria-label={`${monthYear}년 월 선택`}>
            {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => {
              const value = `${monthYear}-${String(month).padStart(2, '0')}`
              const selected = form.nhis_payment_months.includes(value)
              return <button key={value} type="button" aria-pressed={selected} className={selected ? 'is-selected' : ''} onClick={() => toggleMonth(month)}>{month}월</button>
            })}
          </div>
          <div className="criteria-editor__month-chips" aria-label="선택한 고지월">
            {[...form.nhis_payment_months].sort().map((value) => {
              const [year, month] = value.split('-')
              return <button key={value} type="button" onClick={() => {
                setForm((prev) => prev && ({ ...prev, nhis_payment_months: prev.nhis_payment_months.filter((item) => item !== value) }))
              }}>{year}년 {Number(month)}월 ×</button>
            })}
          </div>
          {form.nhis_payment_months.length === 0 && <p role="alert">평균에 포함할 고지월을 하나 이상 선택해 주세요.</p>}
        </div>
        <label>자격득실확인서 변동내역 포함 기간 (년)
          <input type="number" min={1} max={10} value={form.nhis_acquisition_loss_years} onChange={(e) => setForm({ ...form, nhis_acquisition_loss_years: Number(e.target.value) })} />
        </label>
        <label className="criteria-editor__supplement-toggle">
          <input type="checkbox" checked={form.supplement.allowed} onChange={(e) => setForm({
            ...form,
            supplement: { allowed: e.target.checked, days: e.target.checked ? (form.supplement.days ?? 7) : null },
          })} />
          서류 보완 허용
        </label>
        <label>보완 기간 (일)
          <input type="number" min={1} max={365} disabled={!form.supplement.allowed} value={form.supplement.days ?? ''} onChange={(e) => setForm({
            ...form,
            supplement: { ...form.supplement, days: Number(e.target.value) || null },
          })} />
        </label>
      </fieldset>

      <button type="button" disabled={busy || form.nhis_payment_months.length === 0 || (form.supplement.allowed && !form.supplement.days)} onClick={() => void save()}>{busy ? '저장 중…' : '기준 저장'}</button>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {!applicantDemo && <table className="criteria-editor__history"><caption>기준 버전 이력</caption><thead><tr><th>버전</th><th>저장 시각</th><th>역할</th></tr></thead><tbody>
        {history.map((item) => <tr key={item.version}><td>v{item.version}</td><td>{item.changed_at ?? '-'}</td><td>{item.changed_role ?? '-'}</td></tr>)}
      </tbody></table>}
    </section>
  )
}
