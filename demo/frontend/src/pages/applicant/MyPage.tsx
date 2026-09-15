/**
 * 마이페이지 (계획서 3.1절 [7]).
 *
 *   · 진행 상태 5단계: 접수 → 서류검토 → 자격심사 → 선정심사 → 결과발표
 *   · 제출 서류 판독 결과 재확인
 *   · 동의 이력 (수기 서명 없이도 '누가 언제 무엇에 동의했는지'가 남는다)
 *
 * ⚠️ **심사 점수를 표시하지 않는다** (R5.3 / 공고문 "평가결과는 공개하지 않음").
 *    서버 응답(`/status`)에 애초에 점수가 없고, 이 화면도 점수를 계산하지 않는다.
 *    점수 표시를 추가해 달라는 요청이 오면 공고문 문구를 먼저 확인할 것.
 */

import { useEffect, useState } from 'react'

import { fetchStatus, type ApplicationStatus, type DocStatus } from '../../api.ts'
import './my-page.css'

const STATUS_LABEL: Record<DocStatus, string> = {
  PASS: '적합',
  FAIL: '부적합',
  NEEDS_REVIEW: '확인필요',
}

export default function MyPage({ applicationId }: { applicationId: number }) {
  const [data, setData] = useState<ApplicationStatus | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchStatus(applicationId)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [applicationId])

  if (error) return <p className="flow-error">{error}</p>
  if (!data) return <p className="mypage__loading">불러오는 중…</p>

  return (
    <div className="mypage">
      <section className="mypage__head">
        <div>
          <h2>{data.program_name}</h2>
          <p>
            신청번호 <strong>{data.application_no}</strong>
            {data.submitted_at && ` · 접수 ${data.submitted_at.replace('T', ' ')}`}
          </p>
        </div>
        {data.call_center && <p className="mypage__call">문의 {data.call_center}</p>}
      </section>

      <ol className="mypage__progress">
        {data.progress.map((p, i) => (
          <li key={p.label} className={`mpstep mpstep--${p.state}`}>
            <span className="mpstep__no">{i + 1}</span>
            <span className="mpstep__label">{p.label}</span>
          </li>
        ))}
      </ol>

      <p className="mypage__notice">{data.result_notice}</p>

      {/* 선착순 접수 순번 (R6). 점수제 사업에서는 서버가 null을 준다. */}
      {data.first_come && (
        <section className="mypage__queue">
          <strong>접수 순번 {data.first_come.position}번</strong>
          {data.first_come.quota !== null && (
            <span>
              총 지원규모 {data.first_come.quota.toLocaleString('ko-KR')}건 · 남은 규모{' '}
              {(data.first_come.remaining ?? 0).toLocaleString('ko-KR')}건
            </span>
          )}
          <span className="mypage__queue-note">{data.first_come.notice}</span>
        </section>
      )}

      {/* 7일 보완 기한 카운트다운 (E12). 미보완 시 후순위자에게 자리가 넘어간다. */}
      {data.supplement && (
        <section
          className={
            data.supplement.expired
              ? 'mypage__supplement mypage__supplement--over'
              : 'mypage__supplement'
          }
        >
          <div className="mypage__countdown">
            <span className="mypage__days">
              {data.supplement.expired ? '기한 종료' : `D-${data.supplement.days_left}`}
            </span>
            <span>
              보완 기한 {data.supplement.deadline.replace('T', ' ')}
              {!data.supplement.expired && ` (약 ${data.supplement.hours_left}시간 남음)`}
            </span>
          </div>
          <p>{data.supplement.notice}</p>
          {data.supplement.targets.length > 0 && (
            <ul className="mypage__supplement-list">
              {data.supplement.targets.map((t) => (
                <li key={t.label}>
                  <strong>{t.label}</strong> — {t.reason}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* 항목별 지급 예정액. 점수와 달리 이 값은 신청자에게 보여 주는 것이 맞다. */}
      {data.subsidy && data.subsidy.lines.length > 0 && (
        <section className="mypage__box">
          <h3>신청한 지원 항목</h3>
          <table className="mypage__docs">
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
                  <td>{line.label}</td>
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
                  <strong>{data.subsidy.total_granted.toLocaleString('ko-KR')}원</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      )}

      <section className="mypage__box">
        <h3>제출한 서류</h3>
        <table className="mypage__docs">
          <thead>
            <tr>
              <th>파일</th>
              <th>판독된 서류</th>
              <th>판정</th>
              <th>내용</th>
            </tr>
          </thead>
          <tbody>
            {data.documents.map((d) => {
              const status = d.status ?? 'NEEDS_REVIEW'
              return (
                <tr key={d.document_id}>
                  <td>{d.file_name}</td>
                  <td>{d.detected_doc_type ?? '미판별'}</td>
                  <td>
                    <span className={`dstatus dstatus--${status.toLowerCase()}`}>
                      {STATUS_LABEL[status]}
                    </span>
                  </td>
                  <td className="mypage__extract">
                    {Object.entries(d.extracted)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(' · ') || '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section className="mypage__box">
        <h3>동의 이력</h3>
        <ul className="mypage__consents">
          {data.consents.map((c) => (
            <li key={c.consent_type}>
              <span>{c.label}</span>
              <span>{c.agreed ? '동의함' : '동의하지 않음'}</span>
              <span className="mypage__time">
                {c.agreed_at.replace('T', ' ')}
                {c.signature_kind === 'electronic' && ' · 전자서명'}
                {c.signature_kind === 'handwritten' && ' · 자필서명 스캔'}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
