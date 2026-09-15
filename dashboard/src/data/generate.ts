import { addBusinessDays, addDays, at, HOUR_MS } from '../lib/dates'
import { createRandom, type Random } from '../lib/random'
import { decisionAt } from './lifecycle'
import { REGIONS } from './regions'
import { AGE_BANDS, compareApplicants, totalScore } from './scoring'
import {
  GENDERS,
  INSURANCE_TYPES,
  WORK_TYPES,
  type Application,
  type Dataset,
  type RegionName,
  type RejectStage,
} from './types'

// ---------------------------------------------------------------------------
// 목업 데이터 생성기
// 규모·일정·배점은 '26년 공고문/시행지침/운영성과 자료 기준, 분포 비율은 가정값.
// ---------------------------------------------------------------------------

const OPEN_AT = at(2026, 3, 3, 9)
const CLOSE_AT = at(2026, 3, 16, 18)
const REVIEW_START_AT = at(2026, 3, 17, 9)
const ANNOUNCEMENT_AT = at(2026, 5, 15, 10)

/** 신청기간 14일의 일별 접수 비중 — 첫날 몰림('26년 1일 최대 방문 3/3), 마감 직전 반등 */
const DAILY_WEIGHTS = [16, 10, 8, 6.5, 5, 4.5, 5.5, 5, 5.5, 5.5, 5, 6, 8, 10.5]

/** 시군은 정원의 120%를 1차 선정해 도에 제출 */
const FIRST_SELECTION_RATIO = 1.2

const REJECT_RATES = { document: 0.09, eligibility: 0.11, duplicate: 0.015 }

interface WeightedReason {
  reason: string
  weight: number
}

/** 공고문 '미비 서류 예시' 및 콜센터 제출서류 문의 유형 반영 */
const DOCUMENT_REASONS: WeightedReason[] = [
  { reason: '주민등록초본 대신 등본 제출', weight: 24 },
  { reason: 'PDF 암호 미해제', weight: 22 },
  { reason: '초본 주소변동 이력 누락', weight: 16 },
  { reason: '행정정보 동의서 자필서명 누락', weight: 14 },
  { reason: '건강보험 증빙서류 누락', weight: 12 },
  { reason: '공고일 이전 발급 서류', weight: 7 },
  { reason: '식별 불가(화질·화면 캡처)', weight: 5 },
]

const ELIGIBILITY_REASONS: WeightedReason[] = [
  { reason: '건보료 고지액 기준 중위소득 140% 초과', weight: 34 },
  { reason: '근로기간 5개월 미달(근로 공백)', weight: 28 },
  { reason: '유사 자산형성사업 참여·수혜', weight: 16 },
  { reason: '공무원·공공기관 등 제외대상', weight: 10 },
  { reason: '주민등록 거주요건 미충족', weight: 7 },
  { reason: '연령 기준 외', weight: 5 },
]

const DUPLICATE_REASON = '타 사업 중복 수혜(2차 조회)'

/** 콜센터 만족도 조사 응답자 연령대 비율(12/33/30/25%) 참고 */
const AGE_BAND_WEIGHTS = [12, 33, 30, 25]
const YOUNGEST_AGE_WEIGHTS = [2, 4, 8, 14, 20, 24, 28] // 18~24세
const WORK_BAND_WEIGHTS_BY_AGE_BAND = [
  [55, 30, 10, 5],
  [38, 25, 17, 20],
  [28, 20, 15, 37],
  [24, 17, 14, 45],
]

export function generateDataset(seed = 20260303): Dataset {
  const rng = createRandom(seed)
  const applications: Application[] = []
  const firstSelectionAt = {} as Record<RegionName, number>
  let sequence = 0

  for (const region of REGIONS) {
    const submitted: Application[] = []
    for (let i = 0; i < region.applicants; i++) {
      submitted.push(createApplication(rng, region.name, ++sequence))
    }

    scheduleReviews(rng, submitted, region.reviewBusinessDays)
    selectApplications(submitted, region.quota)

    const lastDecision = submitted.reduce((latest, app) => Math.max(latest, decisionAt(app) ?? 0), 0)
    firstSelectionAt[region.name] = addBusinessDays(lastDecision, 2) + 10 * HOUR_MS
    applications.push(...submitted)
  }

  const secondVerificationAt =
    addBusinessDays(Math.max(...Object.values(firstSelectionAt)), 3) + 15 * HOUR_MS

  return {
    applications,
    schedule: {
      openAt: OPEN_AT,
      closeAt: CLOSE_AT,
      reviewStartAt: REVIEW_START_AT,
      firstSelectionAt,
      secondVerificationAt,
      announcementAt: ANNOUNCEMENT_AT,
    },
  }
}

function createApplication(rng: Random, region: RegionName, sequence: number): Application {
  const ageBand = rng.weightedIndex(AGE_BAND_WEIGHTS)
  const age =
    ageBand === 0
      ? AGE_BANDS[0].min + rng.weightedIndex(YOUNGEST_AGE_WEIGHTS)
      : rng.int(AGE_BANDS[ageBand].min, AGE_BANDS[ageBand].max)

  const workType = rng.weighted(WORK_TYPES, [66, 14, 5, 12, 3])
  const selfEmployed = workType === '사업자' || workType === '농어업인'
  const insuranceType = selfEmployed
    ? rng.chance(0.85)
      ? INSURANCE_TYPES[1]
      : INSURANCE_TYPES[0]
    : rng.weighted(INSURANCE_TYPES, [90, 4, 6])

  const incomeBand = rng.weightedIndex([42, 16, 14, 13, 15])
  const residenceBand = rng.weightedIndex([6, 5, 5, 4, 4, 76])
  const workBand = rng.weightedIndex(WORK_BAND_WEIGHTS_BY_AGE_BAND[ageBand])
  const gender = rng.chance(0.45) ? GENDERS[0] : GENDERS[1]
  const householdSize = rng.weighted([1, 2, 3, 4, 5, 6], [40, 21, 17, 15, 5, 2])
  const submittedAt = sampleSubmitTime(rng)

  let rejectStage: RejectStage | null = null
  let rejectReason: string | null = null
  const roll = rng.next()
  if (roll < REJECT_RATES.document) {
    rejectStage = 'document'
    rejectReason = pickReason(rng, DOCUMENT_REASONS)
  } else if (roll < REJECT_RATES.document + REJECT_RATES.eligibility) {
    rejectStage = 'eligibility'
    rejectReason = pickReason(rng, ELIGIBILITY_REASONS)
  } else if (roll < REJECT_RATES.document + REJECT_RATES.eligibility + REJECT_RATES.duplicate) {
    rejectStage = 'duplicate'
    rejectReason = DUPLICATE_REASON
  }

  return {
    id: `JB26-${String(sequence).padStart(5, '0')}`,
    region,
    submittedAt,
    age,
    gender,
    workType,
    insuranceType,
    householdSize,
    incomeBand,
    residenceBand,
    workBand,
    score: totalScore(incomeBand, residenceBand, workBand, age),
    docReviewedAt: null,
    eligibilityReviewedAt: null,
    rejectStage,
    rejectReason,
    firstSelected: false,
    finalSelected: false,
  }
}

function pickReason(rng: Random, reasons: WeightedReason[]): string {
  return reasons[rng.weightedIndex(reasons.map((item) => item.weight))].reason
}

function sampleSubmitTime(rng: Random): number {
  const day = rng.weightedIndex(DAILY_WEIGHTS)
  const dayStart = addDays(at(2026, 3, 3), day)
  const fromHour = day === 0 ? 9 : 0
  const toHour = day === DAILY_WEIGHTS.length - 1 ? 18 : 24
  let hour = fromHour + rng.next() * (toHour - fromHour)
  // 새벽(0~7시) 접수는 드묾 — 한 번 더 뽑아 비중을 낮춤
  if (hour < 7) hour = fromHour + rng.next() * (toHour - fromHour)
  return dayStart + hour * HOUR_MS
}

/** 접수 순서대로 시군 처리 용량에 맞춰 서류 확인·자격 심사 완료 시각을 배정 */
function scheduleReviews(rng: Random, applications: Application[], businessDays: number): void {
  const queue = [...applications].sort((a, b) => (a.submittedAt ?? 0) - (b.submittedAt ?? 0))
  queue.forEach((app, index) => {
    const dayIndex = Math.min(
      businessDays,
      Math.floor((index / queue.length) * businessDays) + (rng.chance(0.3) ? 1 : 0),
    )
    const decidedAt = addBusinessDays(REVIEW_START_AT, dayIndex) + (9 + rng.next() * 9) * HOUR_MS
    const docDay = addBusinessDays(REVIEW_START_AT, Math.max(0, dayIndex - rng.int(0, 2)))
    const docReviewedAt = Math.min(decidedAt, docDay + (9 + rng.next() * 9) * HOUR_MS)

    if (app.rejectStage === 'document') {
      app.docReviewedAt = decidedAt
    } else {
      app.docReviewedAt = docReviewedAt
      app.eligibilityReviewedAt = decidedAt
    }
  })
}

/** 심사표 순위로 1차(120%)·최종(100%) 선정. 2차 중복 조회 대상은 최종 선정에서 빠짐 */
function selectApplications(applications: Application[], quota: number): void {
  const ranked = applications
    .filter((app) => app.rejectStage === null || app.rejectStage === 'duplicate')
    .sort(compareApplicants)

  ranked.slice(0, Math.ceil(quota * FIRST_SELECTION_RATIO)).forEach((app) => {
    app.firstSelected = true
  })
  ranked
    .filter((app) => app.rejectStage === null)
    .slice(0, quota)
    .forEach((app) => {
      app.firstSelected = true
      app.finalSelected = true
    })
}
