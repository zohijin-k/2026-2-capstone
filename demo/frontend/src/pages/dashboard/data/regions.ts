import type { RegionName } from './types'

export interface RegionProfile {
  name: RegionName
  /** '26년 공고 시군별 선정 인원 */
  quota: number
  /** 목업 신청 규모 — '26년 시군별 실제 접수인원 */
  applicants: number
  /** 시군 1차 심사를 끝내는 데 걸리는 영업일 (목업 가정값) */
  reviewBusinessDays: number
}

export const REGIONS: RegionProfile[] = [
  { name: '전주시', quota: 550, applicants: 5828, reviewBusinessDays: 33 },
  { name: '군산시', quota: 180, applicants: 1841, reviewBusinessDays: 24 },
  { name: '익산시', quota: 200, applicants: 2051, reviewBusinessDays: 26 },
  { name: '정읍시', quota: 75, applicants: 532, reviewBusinessDays: 14 },
  { name: '남원시', quota: 50, applicants: 372, reviewBusinessDays: 12 },
  { name: '김제시', quota: 50, applicants: 463, reviewBusinessDays: 15 },
  { name: '완주군', quota: 60, applicants: 800, reviewBusinessDays: 19 },
  { name: '진안군', quota: 15, applicants: 129, reviewBusinessDays: 8 },
  { name: '무주군', quota: 15, applicants: 128, reviewBusinessDays: 9 },
  { name: '장수군', quota: 15, applicants: 78, reviewBusinessDays: 6 },
  { name: '임실군', quota: 15, applicants: 80, reviewBusinessDays: 7 },
  { name: '순창군', quota: 15, applicants: 33, reviewBusinessDays: 5 },
  { name: '고창군', quota: 30, applicants: 230, reviewBusinessDays: 11 },
  { name: '부안군', quota: 30, applicants: 256, reviewBusinessDays: 10 },
]

export const REGION_BY_NAME = Object.fromEntries(REGIONS.map((region) => [region.name, region])) as Record<
  RegionName,
  RegionProfile
>

export const TOTAL_QUOTA = REGIONS.reduce((sum, region) => sum + region.quota, 0)
