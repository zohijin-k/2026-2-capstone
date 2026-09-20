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
  docReviewedAt: number | null
  eligibilityReviewedAt: number | null
  rejectStage: RejectStage | null
  rejectReason: string | null
  /** 시군 1차 선정(정원의 120%) 포함 여부 */
  firstSelected: boolean
  /** 최종 선정 여부 */
  finalSelected: boolean
}

/**
 * 배점 정보. **담당자만 볼 수 있다.**
 *
 * `Application`에 섞지 않고 배열을 따로 두는 이유: 같은 행에 담아 두고 권한에 따라
 * 값을 지우는 방식은 한 군데만 빠뜨려도 조용히 새어나간다. 배열째 있거나 없거나면
 * 누락이 구조적으로 불가능하다. 서버도 같은 계약으로 내려준다
 * (`demo/backend/api/dashboard.py`).
 */
export interface ScoreRow {
  id: string
  /** 심사표 구간 인덱스 (scoring.ts 참고) */
  incomeBand: number
  residenceBand: number
  workBand: number
  /** 신청서 기재값 기준 심사표 총점 */
  score: number
}

/** 목업 생성기 안에서만 쓰는 합본. 화면으로는 두 갈래로 나뉘어 나간다. */
export type ScoredApplication = Application & Omit<ScoreRow, 'id'>

/** 지금 화면이 무엇을 보고 있는가. 배지와 각주가 읽는다. */
export type DataSource = 'mock' | 'live'

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
  source: DataSource
  /** 없으면 배점 분포·커트라인을 아예 그리지 않는다. */
  scores?: ScoreRow[]
  /** 배점을 왜 빼고 받았는지. 담당자용 구역에 그대로 띄운다. */
  scoresWithheldReason?: string | null
  /** 실데이터에서 제외했거나 근사한 사실. 화면 각주로 띄운다. */
  notes?: string[]
  /** 시군별 정원. 실데이터는 서버가 정본을 내려준다. */
  quotaByRegion?: Partial<Record<RegionName, number>>
}
