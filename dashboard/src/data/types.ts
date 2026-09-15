export const REGION_NAMES = [
  '전주시',
  '군산시',
  '익산시',
  '정읍시',
  '남원시',
  '김제시',
  '완주군',
  '진안군',
  '무주군',
  '장수군',
  '임실군',
  '순창군',
  '고창군',
  '부안군',
] as const

export type RegionName = (typeof REGION_NAMES)[number]

export const GENDERS = ['남성', '여성'] as const
export type Gender = (typeof GENDERS)[number]

export const WORK_TYPES = ['상용직', '임시직', '일용직', '사업자', '농어업인'] as const
export type WorkType = (typeof WORK_TYPES)[number]

export const INSURANCE_TYPES = ['직장가입자', '지역가입자', '혼합가입자'] as const
export type InsuranceType = (typeof INSURANCE_TYPES)[number]

/** document: 읍면동 서류 확인, eligibility: 시군 자격 심사, duplicate: 도·허브센터 2차 중복 조회 */
export type RejectStage = 'document' | 'eligibility' | 'duplicate'

export interface Application {
  id: string
  region: RegionName
  /** 최종 제출(접수) 시각(ms) */
  submittedAt: number | null
  /** 2025.12.31. 기준 만 나이 */
  age: number
  gender: Gender
  workType: WorkType
  insuranceType: InsuranceType
  householdSize: number
  /** 심사표 구간 인덱스 (scoring.ts 참고) */
  incomeBand: number
  residenceBand: number
  workBand: number
  /** 신청서 기재값 기준 심사표 총점 */
  score: number
  docReviewedAt: number | null
  eligibilityReviewedAt: number | null
  rejectStage: RejectStage | null
  rejectReason: string | null
  /** 시군 1차 선정(정원의 120%) 포함 여부 */
  firstSelected: boolean
  /** 최종 선정 여부 */
  finalSelected: boolean
}

export interface Schedule {
  openAt: number
  closeAt: number
  reviewStartAt: number
  firstSelectionAt: Record<RegionName, number>
  secondVerificationAt: number
  announcementAt: number
}

export interface Dataset {
  applications: Application[]
  schedule: Schedule
}
