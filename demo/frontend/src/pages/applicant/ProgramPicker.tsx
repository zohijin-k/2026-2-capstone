/**
 * 사업 선택 (P5).
 *
 * 같은 파이프라인이 사업만 바꿔서 도는지를 눈으로 보여주는 화면이다. 두 카드가
 * 나란히 놓이고, 고르는 순간 이후 모든 화면(자가진단 문항 수·신청서 항목·서류
 * 체크리스트·판정 기준일)이 갈린다.
 *
 * 카드에 적히는 값은 전부 서버의 `ProgramConfig`에서 온다. 화면이 상수를 따로
 * 들고 있으면 사업 설정을 고쳐도 카드가 옛 값을 말하게 된다.
 *
 * 카드 본문은 세 가지다. 서버가 `detail`을 채워 보낸 사업은 공고문 차례대로
 * 펼치고(`DetailBody`), `package_detail`을 채워 보낸 사업은 사업계획서 차례대로
 * 펼치며(`PackageBody`), 둘 다 없는 사업은 요약 행만 보여준다(`SummaryBody`).
 */

import { useEffect, useState } from 'react'

import {
  fetchPrograms,
  type PackageDetail,
  type Program,
  type ProgramDetail,
} from '../../api.ts'
import './program-picker.css'

const dash = (value: string) => value.replaceAll('-', '. ')

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

/** '2026-03-03' → '2026. 3. 3.(화)'. 공고문 날짜 표기 그대로. */
function korDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return `${y}. ${m}. ${d}.(${WEEKDAYS[new Date(y, m - 1, d).getDay()]})`
}

/** 100000 → '10만 원'. 공고문이 만 원 단위로 적는다. */
const manwon = (won: number) => `${(won / 10_000).toLocaleString('ko-KR')}만 원`

/** 시군별 정원표를 좁은 카드 폭에 맞춰 여러 줄로 자른다. */
function chunk<T>(list: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}

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

/** 기존 요약 카드 본문. 상세를 채우지 않은 사업이 쓴다. */
function SummaryBody({ p }: { p: Program }) {
  return (
    <>
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
    </>
  )
}

/** 공고문 전문을 펼친 카드 본문. 절 순서가 공고문 순서다. */
function DetailBody({ p, d }: { p: Program; d: ProgramDetail }) {
  const plan = d.savings_plan
  const regions = Object.entries(p.quota_by_region ?? {})

  return (
    <div className="pdetail">
      <section className="pdetail__sec">
        <h3>지원 개요</h3>
        <ul className="pdetail__list">
          <li>
            <b>지원 대상:</b> {d.target_summary}
            <ul>
              {d.target_points.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </li>
          <li>
            <b>지원 내용:</b> {d.benefit_summary}
          </li>
        </ul>

        {plan && (
          <table className="pdetail__table pdetail__table--num">
            <thead>
              <tr>
                <th>청년 월 저축액</th>
                <th>지자체 월 지원액</th>
                <th>만기 수령액({plan.months}개월)</th>
                <th>비고</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{manwon(plan.monthly_self)}</td>
                <td>{manwon(plan.monthly_grant)}</td>
                <td>{plan.maturity_label}</td>
                <td className="pdetail__td--text">{plan.note}</td>
              </tr>
            </tbody>
          </table>
        )}
      </section>

      <section className="pdetail__sec">
        <h3>모집 및 신청 일정</h3>
        <ul className="pdetail__list">
          <li>
            <b>공고 기간:</b> {korDate(d.announce_period[0])} ~ {korDate(d.announce_period[1])}
          </li>
          <li>
            <b>신청 기간:</b> {korDate(p.apply_period[0])} {d.apply_open_time} ~{' '}
            {korDate(p.apply_period[1])} {d.apply_close_time}
          </li>
          <li>
            <b>신청 방법:</b> {d.apply_method}
            <ol>
              {d.apply_steps.map((s) => (
                <li key={s.label}>
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.label}
                    </a>
                  ) : (
                    s.label
                  )}
                </li>
              ))}
            </ol>
          </li>
        </ul>
      </section>

      <section className="pdetail__sec">
        <h3>신청 시 유의사항</h3>
        <p className="pdetail__warn">
          <b>중요:</b> {d.deadline_warning}
        </p>
        <ul className="pdetail__list">
          {d.cautions.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>

        <h4>미비 서류 예시</h4>
        <ul className="pdetail__list">
          {d.missing_doc_examples.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </section>

      {regions.length > 0 && (
        <section className="pdetail__sec">
          <h3>선정 인원</h3>
          <p className="pdetail__total">
            <b>총 {(p.quota_total ?? 0).toLocaleString('ko-KR')}명</b>
          </p>
          {chunk(regions, 7).map((part) => (
            <table key={part[0][0]} className="pdetail__table pdetail__table--num">
              <thead>
                <tr>
                  {part.map(([name]) => (
                    <th key={name}>{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {part.map(([name, count]) => (
                    <td key={name}>{count.toLocaleString('ko-KR')}명</td>
                  ))}
                </tr>
              </tbody>
            </table>
          ))}
        </section>
      )}

      <section className="pdetail__sec">
        <h3>선정 방법</h3>
        <ul className="pdetail__list">
          {d.selection_methods.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>
    </div>
  )
}

/** 신청 기간 한 줄. 1차는 `apply_period`, 2차는 `apply_period_2`에서 온다. */
function rounds(p: Program): { label: string; value: string }[] {
  const out = [
    { label: '1차', value: `${korDate(p.apply_period[0])} ~ ${korDate(p.apply_period[1])}` },
  ]
  if (p.apply_period_2) {
    out.push({
      label: '2차',
      value: `${korDate(p.apply_period_2[0])} ~ ${korDate(p.apply_period_2[1])}`,
    })
  }
  return out
}

/**
 * 사업계획서를 펼친 카드 본문. 절 순서가 사업계획서 순서다 —
 * 사업신청 → 서류심사 → 지원금 지급.
 *
 * 금액·횟수·지원 항목은 `d`가 아니라 `p.subsidy_catalog`에서 읽는다. 지원 항목표가
 * 유일한 출처이고, 여기서 상수를 다시 적으면 두 곳이 갈라진다.
 */
function PackageBody({ p, d }: { p: Program; d: PackageDetail }) {
  const catalog = p.subsidy_catalog ?? []

  return (
    <div className="pdetail">
      <dl className="pkg__summary">
        {rounds(p).map((r) => (
          <div key={r.label}>
            <dt>{r.label} 신청</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
        {p.quota_total !== null && (
          <div>
            <dt>지원 규모</dt>
            <dd>총 {p.quota_total.toLocaleString('ko-KR')}건</dd>
          </div>
        )}
      </dl>

      <section className="pdetail__sec">
        <h3>1. 사업신청</h3>

        <h4>신청 기간</h4>
        <dl className="pkg__rounds">
          {rounds(p).map((r) => (
            <div key={r.label}>
              <dt>{r.label}</dt>
              <dd>{r.value}</dd>
            </div>
          ))}
        </dl>
        <p className="pkg__note">{d.early_close_note}</p>

        <h4>신청 대상</h4>
        <ul className="pdetail__list">
          {d.target_points.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>

        <h4>신청 방법</h4>
        <ul className="pdetail__list">
          <li>
            {p.site_url ? (
              <a href={p.site_url} target="_blank" rel="noreferrer">
                {d.apply_method}
              </a>
            ) : (
              d.apply_method
            )}
          </li>
        </ul>

        <h4>신청 가능 항목</h4>
        <ul className="pkg__chips">
          {catalog.map((c) => (
            <li key={c.item_type}>{c.label}</li>
          ))}
        </ul>
        <p className="pkg__note">{d.apply_items_note}</p>

        <h4>신청 서류</h4>
        <p className="pkg__sublabel">공통서류</p>
        <ol className="pdetail__list">
          {d.common_docs.map((doc) => (
            <li key={doc}>{doc}</li>
          ))}
        </ol>

        <p className="pkg__sublabel">항목별 추가서류</p>
        <div className="pkg__scroll">
          <table className="pdetail__table pkg__table--docs">
            <colgroup>
              <col className="pkg__col--item" />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">지원 항목</th>
                <th scope="col">추가서류</th>
              </tr>
            </thead>
            <tbody>
              {d.item_docs.map((row) => (
                <tr key={row.item}>
                  <th scope="row">{row.item}</th>
                  <td>{row.docs.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="pdetail__warn">
          <b>{d.doc_cutoff_notice}</b>
        </p>
      </section>

      <section className="pdetail__sec">
        <h3>2. 서류심사</h3>
        <ol className="pkg__steps">
          {d.review_steps.map((step) => (
            <li key={step.title}>
              <b>{step.title}</b>
              <ul>
                {step.points.map((pt) => (
                  <li key={pt}>{pt}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
        <ul className="pdetail__list">
          {d.supplement_notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </section>

      <section className="pdetail__sec">
        <h3>3. 지원금 지급</h3>

        {p.quota_total !== null && (
          <>
            <h4>지원 규모</h4>
            <ul className="pdetail__list">
              <li>총 {p.quota_total.toLocaleString('ko-KR')}건</li>
            </ul>
          </>
        )}

        <h4>지원 내용</h4>
        <div className="pkg__scroll">
          <table className="pdetail__table pdetail__table--num pkg__table--benefit">
            <colgroup>
              <col className="pkg__col--item" />
              <col />
              <col className="pkg__col--amount" />
              <col className="pkg__col--count" />
            </colgroup>
            <thead>
              <tr>
                <th scope="col" className="pdetail__td--text">
                  지원 항목
                </th>
                <th scope="col" className="pdetail__td--text">
                  지원 내용
                </th>
                <th scope="col">지원금액</th>
                <th scope="col">지원 횟수</th>
              </tr>
            </thead>
            <tbody>
              {catalog.map((c) => (
                <tr key={c.item_type}>
                  <th scope="row" className="pdetail__td--text">
                    {c.label}
                  </th>
                  <td className="pdetail__td--text">{c.description}</td>
                  <td>{c.amount_label}</td>
                  <td>{c.count_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h4>지급 방법</h4>
        <ul className="pdetail__list">
          {d.payment_methods.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </section>
    </div>
  )
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
              {!p.detail && (
                <span
                  className={
                    p.is_first_come ? 'pcard__tag pcard__tag--fcfs' : 'pcard__tag'
                  }
                >
                  {p.is_first_come ? '선착순' : '점수제'}
                </span>
              )}
              {p.package_detail && (
                <span className="pcard__hint">{p.package_detail.early_close_note}</span>
              )}
            </div>

            {p.detail ? (
              <DetailBody p={p} d={p.detail} />
            ) : p.package_detail ? (
              <PackageBody p={p} d={p.package_detail} />
            ) : (
              <SummaryBody p={p} />
            )}

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
