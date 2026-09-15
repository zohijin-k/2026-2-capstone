/**
 * 서식1의 기간 구간 자동 판정.
 *
 * 서식1은 거주기간(6구간)·근로기간(4구간)을 체크박스로 받는다. 신청자가 직접
 * 고르면 틀리기 쉬우므로, 날짜만 받아 구간을 자동으로 정하고 근거 문장을 같이
 * 보여준다. 체크박스 자체는 서식 원형대로 남긴다.
 *
 * 기준일은 공고일(2026-03-03). 시행지침 서식6의 "공고일 기준으로 역산정"과
 * 같은 규칙이라, 채점(P3)과 여기가 어긋나면 안 된다.
 */

export const ANNOUNCEMENT_DATE = '2026-03-03'

/** 서식1 거주기간 6구간 — 원문 표기 그대로. */
export const RESIDENCE_BUCKETS = [
  '1년 미만',
  '1년 이상 ~ 2년 미만',
  '2년 이상 ~ 3년 미만',
  '3년 이상 ~ 4년 미만',
  '4년 이상 ~ 5년 미만',
  '5년 이상',
] as const

/** 서식1 현직장 근로기간 4구간 — 원문 표기 그대로. */
export const WORK_BUCKETS = [
  '1년 미만',
  '1년 이상 ~ 2년 미만',
  '2년 이상 ~ 3년 미만',
  '3년 이상',
] as const

export interface DerivedPeriod {
  /** 선택된 구간 라벨. 날짜가 없거나 기준일보다 뒤면 null. */
  bucket: string | null
  /** 화면에 보여줄 근거 한 줄. */
  basis: string
  years: number
  months: number
}

/** `from` 부터 `to` 까지 만 경과 연/월. */
function elapsed(from: Date, to: Date): { years: number; months: number } {
  let months = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth())
  if (to.getDate() < from.getDate()) months -= 1
  return { years: Math.floor(months / 12), months: months % 12 }
}

function bucketOf(years: number, buckets: readonly string[]): string {
  // 마지막 구간이 "N년 이상"이므로 상한을 넘으면 마지막으로 모은다.
  return buckets[Math.min(years, buckets.length - 1)]
}

function derive(
  isoDate: string,
  buckets: readonly string[],
  label: string,
  basisDate = ANNOUNCEMENT_DATE,
): DerivedPeriod {
  if (!isoDate) {
    return { bucket: null, basis: `${label}을 입력하면 해당 구간이 자동 선택됩니다.`, years: 0, months: 0 }
  }
  const from = new Date(isoDate)
  const to = new Date(basisDate)
  if (Number.isNaN(from.getTime()) || from > to) {
    return {
      bucket: null,
      basis: `${label}이 공고일(${basisDate})보다 뒤입니다. 다시 확인해 주세요.`,
      years: 0,
      months: 0,
    }
  }
  const { years, months } = elapsed(from, to)
  const span = years > 0 ? `${years}년 ${months}개월` : `${months}개월`
  return {
    bucket: bucketOf(years, buckets),
    basis: `${isoDate} ${label} → 공고일(${basisDate})까지 ${span}`,
    years,
    months,
  }
}

export function deriveResidence(transferInDate: string): DerivedPeriod {
  return derive(transferInDate, RESIDENCE_BUCKETS, '전입')
}

export function deriveWork(employmentDate: string): DerivedPeriod {
  return derive(employmentDate, WORK_BUCKETS, '취업')
}
