import type { Application } from './types'

/** '26년 참여자 선정 심사표 (시행지침 서식6) */
export const INCOME_BANDS = [
  { label: '100% 미만', points: 40 },
  { label: '100~110%', points: 37 },
  { label: '110~120%', points: 34 },
  { label: '120~130%', points: 31 },
  { label: '130% 이상', points: 28 },
] as const

export const RESIDENCE_BANDS = [
  { label: '1년 미만', points: 15 },
  { label: '1~2년', points: 17 },
  { label: '2~3년', points: 19 },
  { label: '3~4년', points: 21 },
  { label: '4~5년', points: 23 },
  { label: '5년 이상', points: 25 },
] as const

export const WORK_BANDS = [
  { label: '1년 미만', points: 16 },
  { label: '1~2년', points: 19 },
  { label: '2~3년', points: 22 },
  { label: '3년 이상', points: 25 },
] as const

export const AGE_BANDS = [
  { label: '24세 이하', min: 18, max: 24, points: 10 },
  { label: '25~29세', min: 25, max: 29, points: 9 },
  { label: '30~34세', min: 30, max: 34, points: 8 },
  { label: '35세 이상', min: 35, max: 39, points: 7 },
] as const

export const MIN_AGE = AGE_BANDS[0].min
export const MAX_AGE = AGE_BANDS[AGE_BANDS.length - 1].max

export const MIN_SCORE =
  INCOME_BANDS[INCOME_BANDS.length - 1].points +
  RESIDENCE_BANDS[0].points +
  WORK_BANDS[0].points +
  AGE_BANDS[AGE_BANDS.length - 1].points
export const MAX_SCORE = 100

export function ageBandIndex(age: number): number {
  return AGE_BANDS.findIndex((band) => age >= band.min && age <= band.max)
}

export function totalScore(incomeBand: number, residenceBand: number, workBand: number, age: number): number {
  return (
    INCOME_BANDS[incomeBand].points +
    RESIDENCE_BANDS[residenceBand].points +
    WORK_BANDS[workBand].points +
    AGE_BANDS[ageBandIndex(age)].points
  )
}

/** 고득점 순, 동점 시 ①가구소득이 적은 ②도 거주기간이 긴 ③근로기간이 긴 ④연령이 낮은 순 */
export function compareApplicants(a: Application, b: Application): number {
  return (
    b.score - a.score ||
    a.incomeBand - b.incomeBand ||
    b.residenceBand - a.residenceBand ||
    b.workBand - a.workBand ||
    a.age - b.age ||
    a.id.localeCompare(b.id)
  )
}
