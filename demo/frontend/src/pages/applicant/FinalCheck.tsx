/**
 * 제출 전 최종 확인 (계획서 3.1절 [5]).
 *
 * 두배적금은 **보완 요청이 없는 사업**이다. 제출 버튼을 누르는 순간이 마지막
 * 기회이고, 그 사실을 화면에서 숨기면 안 된다. 그래서 이 화면은 세 가지만 한다.
 *
 *   1. 남은 부적합·누락을 한 곳에 모으고, 각각 **고칠 수 있는 위치로 보낸다**
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
  type DocStatus,
  type FinalCheck as FinalCheckData,
  type SubmitResult,
} from '../../api.ts'
import './final-check.css'

const STATUS_LABEL: Record<DocStatus, string> = {
  PASS: '적합',
  FAIL: '부적합',
  NEEDS_REVIEW: '확인필요',
}

const KIND_LABEL: Record<Blocker['kind'], string> = {
  form: '신청서',
  consent: '동의',
  document: '서류',
  context: '근로유형',
}

const GOTO_LABEL: Record<Blocker['goto'], string> = {
  form1: '신청서로 이동',
  consent: '동의 화면으로 이동',
  upload: '업로드 화면으로 이동',
}

export default function FinalCheck({
  applicationId,
  onGoto,
  onSubmitted,
}: {
  applicationId: number
  onGoto: (blocker: Blocker) => void
  onSubmitted: (result: SubmitResult) => void
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
      {!data.allows_supplement && (
        <section className="fcheck__alarm">
          <h3>이 사업은 서류를 보완할 기회가 없습니다</h3>
          <p>
            {data.program_name}은(는) 서류 미비가 있어도 <strong>별도의 보완(추가서류)
            요청 없이 선발에서 제외</strong>됩니다. 제출 후에는 고칠 수 없으니, 아래 내용을
            지금 확인해 주세요.
          </p>
        </section>
      )}

      {data.warnings
        .filter((w) => data.allows_supplement || !w.includes('보완'))
        .map((w) => (
          <p key={w} className="fcheck__warn">
            {w}
          </p>
        ))}

      <section className="fcheck__box">
        <h3>제출할 수 있는 상태인가</h3>
        {data.blockers.length === 0 ? (
          <p className="fcheck__ok">
            확인이 필요한 항목이 없습니다. 아래 내용을 마지막으로 확인한 뒤 제출해 주세요.
          </p>
        ) : (
          <ul className="fcheck__blockers">
            {data.blockers.map((b) => (
              <li key={`${b.kind}-${b.target}`}>
                <span className="fcheck__kind">{KIND_LABEL[b.kind]}</span>
                <span className="fcheck__msg">{b.message}</span>
                <button type="button" className="btn btn--small" onClick={() => onGoto(b)}>
                  {GOTO_LABEL[b.goto]}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

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
                    <td>{d.file_name}</td>
                    <td>{d.detected_doc_type ?? '미판별'}</td>
                    <td>{d.declared_issue_date ?? '-'}</td>
                    <td>
                      <span className={`dstatus dstatus--${status.toLowerCase()}`}>
                        {STATUS_LABEL[status]}
                      </span>
                    </td>
                    <td className="fcheck__reason">
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
                : `확인이 필요한 항목이 ${data.blockers.length}건 남았습니다`}
        </button>
      </div>
    </div>
  )
}
