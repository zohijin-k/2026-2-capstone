/**
 * 사업 선택 (P5).
 *
 * 같은 파이프라인이 사업만 바꿔서 도는지를 눈으로 보여주는 화면이다. 두 카드가
 * 나란히 놓이고, 고르는 순간 이후 모든 화면(자가진단 문항 수·신청서 항목·서류
 * 체크리스트·판정 기준일)이 갈린다.
 *
 * 카드에 적히는 값은 전부 서버의 `ProgramConfig`에서 온다. 화면이 상수를 따로
 * 들고 있으면 사업 설정을 고쳐도 카드가 옛 값을 말하게 된다.
 */

import { useEffect, useState } from 'react'

import { fetchPrograms, type Program } from '../../api.ts'
import './program-picker.css'

const dash = (value: string) => value.replaceAll('-', '. ')

function rows(p: Program): { label: string; value: string }[] {
  return [
    { label: '선발 방식', value: p.is_first_come ? '선착순 (예산 소진 시 조기 마감)' : '심사표 100점 점수제' },
    {
      label: '서류 보완',
      value: p.allows_supplement
        ? `${p.supplement_days}일 내 보완 가능 (미보완 시 후순위자 선정)`
        : '불가 — 미비 시 보완 요청 없이 선발 제외',
    },
    {
      label: '연령 기준',
      value: `${dash(p.age_basis_date)} 기준 만 18~39세 (${dash(p.birth_range[0])} ~ ${dash(p.birth_range[1])} 출생)`,
    },
    { label: '소득 요건', value: p.has_income_requirement ? '가구 중위소득 140% 이하' : '없음' },
    { label: '서류 인정일', value: `${dash(p.document_cutoff)} 이후 발급분` },
    {
      label: '지원 규모',
      value: p.quota_total === null ? '-' : `${p.quota_total.toLocaleString('ko-KR')}건`,
    },
    {
      label: '신청 기간',
      value: `${dash(p.apply_period[0])} ~ ${dash(p.apply_period[1])}`,
    },
  ]
}

export default function ProgramPicker({
  onPick,
}: {
  onPick: (program: Program) => void
}) {
  const [programs, setPrograms] = useState<Program[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchPrograms()
      .then(setPrograms)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <p className="flow-error">{error}</p>
  if (!programs) return <p className="ppick__loading">사업 목록을 불러오는 중…</p>

  return (
    <div className="ppick">
      <p className="ppick__lead">
        신청할 사업을 고르세요. 사업마다 자격요건·제출서류·선발 방식이 다르며,
        이후 화면은 고른 사업의 기준에 맞춰 자동으로 바뀝니다.
      </p>

      <ul className="ppick__list">
        {programs.map((p) => (
          <li key={p.code} className="pcard">
            <div className="pcard__head">
              <h2>{p.name}</h2>
              <span
                className={
                  p.is_first_come ? 'pcard__tag pcard__tag--fcfs' : 'pcard__tag'
                }
              >
                {p.is_first_come ? '선착순' : '점수제'}
              </span>
            </div>

            <dl className="pcard__rows">
              {rows(p).map((r) => (
                <div key={r.label}>
                  <dt>{r.label}</dt>
                  <dd>{r.value}</dd>
                </div>
              ))}
            </dl>

            {p.subsidy_catalog && (
              <table className="pcard__items">
                <thead>
                  <tr>
                    <th>지원 항목</th>
                    <th>지원금액</th>
                    <th>횟수</th>
                  </tr>
                </thead>
                <tbody>
                  {p.subsidy_catalog.map((c) => (
                    <tr key={c.item_type}>
                      <td>{c.label}</td>
                      <td>{c.amount_label}</td>
                      <td>{c.count_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <ul className="pcard__notes">
              {p.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>

            <button
              type="button"
              className="btn btn--primary pcard__go"
              onClick={() => onPick(p)}
            >
              {p.name} 신청하기
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
