/**
 * 제출 전 최종 확인 (계획서 3.1절 [5]).
 *
 * 두배적금은 **보완 요청이 없는 사업**이다. 제출 버튼을 누르는 순간이 마지막
 * 기회이고, 그 사실을 화면에서 숨기면 안 된다. 그래서 이 화면은 세 가지만 한다.
 *
 *   1. 남은 확인 항목·누락을 한 곳에 모으고, 각각 **고칠 수 있는 위치로 보낸다**
 *   2. 하나라도 남아 있으면 제출 버튼을 잠근다
 *   3. "보완 없음"을 가장 크게 경고한다
 *
 * 점수는 여기에도 나오지 않는다 (R5.3). 화면에 뿌리는 값은 입력값과 서류 판독
 * 결과뿐이다.
 */

import { useEffect, useState } from 'react'

import {
  fetchFinalCheck,
  submitApplication,
  type Blocker,
  type FinalCheck as FinalCheckData,
  type SubmitResult,
} from '../../api.ts'
import FileLink from '../../components/FileLink.tsx'
import StatusBadge from '../../components/StatusBadge.tsx'
import './final-check.css'

/** 남은 항목을 어느 화면에서 고치는지 기준으로 묶는다. 순서는 신청 순서대로. */
type ApplicantStage = 'forms' | 'subsidy' | 'upload'

const BLOCKER_GROUPS: { goto: ApplicantStage; title: string; action: string }[] = [
  { goto: 'forms', title: '신청 서식', action: '서식 작성으로' },
  { goto: 'subsidy', title: '지원 항목', action: '지원 항목으로' },
  { goto: 'upload', title: '서류', action: '서류 업로드로' },
]

function applicantStage(goto: Blocker['goto']): ApplicantStage {
  return goto === 'form1' || goto === 'consent' ? 'forms' : goto
}

export default function FinalCheck({
  applicationId,
  onSubmitted,
  onBack,
  onGoto,
}: {
  applicationId: number
  onSubmitted: (result: SubmitResult) => void
  onBack: () => void
  /** 남은 항목을 고치러 해당 단계로 간다 */
  onGoto: (stage: ApplicantStage) => void
}) {
  const [data, setData] = useState<FinalCheckData | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchFinalCheck(applicationId)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [applicationId])

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      onSubmitted(await submitApplication(applicationId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (error && !data) return <p className="flow-error">{error}</p>
  if (!data) return <p className="fcheck__loading">확인 중…</p>

  return (
    <div className="fcheck">
      {data.first_come && (
        <section className="fcheck__queue">
          <h3>이 사업은 선착순입니다</h3>
          <p>
            {data.first_come.notice} 지금 제출하시면{' '}
            <strong>{data.first_come.position}번째</strong>로 접수됩니다.
          </p>
        </section>
      )}

      {data.warnings.length > 0 && !data.already_submitted && (
        <div className="fcheck__warn">
          {data.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      {!data.already_submitted && data.blockers.length > 0 && (
        <section className="fcheck__todo" aria-labelledby="fcheck-todo">
          <h3 id="fcheck-todo">
            제출 전에 채워야 할 항목 <span>{data.blockers.length}건</span>
          </h3>
          <ul>
            {BLOCKER_GROUPS.map((g) => {
              const items = data.blockers.filter((b) => applicantStage(b.goto) === g.goto)
              if (items.length === 0) return null
              return (
                <li key={g.goto}>
                  <span className="fcheck__todo-title">{g.title}</span>
                  <span className="fcheck__todo-items">
                    {items.map((b) => (
                      <span key={`${b.kind}-${b.target}`} title={b.message}>
                        {b.label}
                      </span>
                    ))}
                  </span>
                  <button type="button" className="btn btn--small" onClick={() => onGoto(g.goto)}>
                    {g.action}
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {data.subsidy && data.subsidy.lines.length > 0 && (
        <section className="fcheck__box">
          <h3>신청하신 지원 항목과 지급 예정액</h3>
          <table className="fcheck__docs">
            <thead>
              <tr>
                <th>항목</th>
                <th>영수증 금액</th>
                <th>지급 예정액</th>
                <th>계산 근거</th>
              </tr>
            </thead>
            <tbody>
              {data.subsidy.lines.map((line) => (
                <tr key={`${line.item_type}-${line.index}`}>
                  <td>{line.label}{line.linked_interview_index && <small className="subsidy__link-note">면접 {line.linked_interview_index}회차와 연결</small>}</td>
                  <td>
                    {line.actual_cost
                      ? line.receipt_amount === null
                        ? '미입력'
                        : `${line.receipt_amount.toLocaleString('ko-KR')}원`
                      : '불요'}
                  </td>
                  <td>
                    <strong>{line.granted_amount.toLocaleString('ko-KR')}원</strong>
                  </td>
                  <td>{line.calculation}</td>
                </tr>
              ))}
              <tr>
                <th colSpan={2}>합계</th>
                <td colSpan={2}>
                  <strong>
                    {data.subsidy.total_granted.toLocaleString('ko-KR')}원
                  </strong>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      )}

      <section className="fcheck__box">
        <h3>작성하신 내용</h3>
        <dl className="fcheck__summary">
          {data.form_summary.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd className={f.value ? undefined : 'is-empty'}>{f.value || '미입력'}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="fcheck__box">
        <h3>제출 서류 판독 결과</h3>
        {data.documents.length === 0 ? (
          <p className="fcheck__empty">아직 올린 서류가 없습니다.</p>
        ) : (
          <table className="fcheck__docs">
            <thead>
              <tr>
                <th>파일</th>
                <th>판독된 서류</th>
                <th>발급일 입력값</th>
                <th>판정</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((d) => {
                const status = d.status ?? 'NEEDS_REVIEW'
                return (
                  <tr key={d.document_id}>
                    <td>
                      <FileLink url={d.file_url} name={d.file_name} format={d.file_format} />
                    </td>
                    <td>{d.detected_doc_type ?? '미판별'}</td>
                    <td>{d.declared_issue_date ?? '-'}</td>
                    <td>
                      <StatusBadge status={status} audience="applicant" />
                    </td>
                    <td className={d.findings.length ? 'fcheck__reason' : 'fcheck__none'}>
                      {d.findings.map((f) => f.message).join(' / ') || '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      {error && <p className="fcheck__error">{error}</p>}

      <div className="flow__actions">
        <button type="button" className="btn" onClick={onBack}>
          이전
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!data.can_submit || busy}
          onClick={() => void submit()}
        >
          {data.already_submitted
            ? '이미 제출된 신청입니다'
            : busy
              ? '제출 중…'
              : data.can_submit
                ? '최종 제출'
                : `${data.blockers.length}건을 채우면 제출할 수 있습니다`}
        </button>
      </div>
    </div>
  )
}
