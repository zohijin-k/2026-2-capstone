import { decisionAt, phaseAt, reviewStageAt, type Phase, type ReviewStage } from '../data/lifecycle'
import { REGIONS } from '../data/regions'
import { ageBandIndex, MAX_AGE, MAX_SCORE, MIN_AGE, MIN_SCORE } from '../data/scoring'
import {
  GENDERS,
  INSURANCE_TYPES,
  WORK_TYPES,
  type Dataset,
  type RegionName,
  type RejectStage,
} from '../data/types'
import { addDays, DAY_MS, startOfDay } from './dates'

/** 판정 건이 적을 때 쓰는 적합률 가정값 */
const DEFAULT_ELIGIBLE_RATE = 0.8
const MIN_DECIDED_FOR_RATE = 30
const SCORE_SLOTS = MAX_SCORE - MIN_SCORE + 1
const HOUSEHOLD_LABELS = ['1인', '2인', '3인', '4인', '5인', '6인 이상']

export interface CutoffEstimate {
  score: number | null
  kind: 'confirmed' | 'estimated' | 'undersubscribed' | 'none'
}

export interface RegionRow {
  name: RegionName
  quota: number
  submitted: number
  waiting: number
  reviewing: number
  eligible: number
  rejected: number
  competition: number
  progress: number
  eligibleRate: number | null
  avgProcessingDays: number | null
  /** 담당자용 — 배점 기반 정보 */
  cutoff: CutoffEstimate
  firstSelected: number
  finalSelected: number
}

export interface DailyPoint {
  date: number
  submitted: number | null
  cumulativeSubmitted: number | null
}

export interface ScoreBin {
  score: number
  withinCutoff: number
  outsideCutoff: number
  rejected: number
}

export interface CountItem {
  label: string
  count: number
}

export interface RejectReasonItem {
  reason: string
  stage: RejectStage
  count: number
}

export interface AgePoint {
  age: number
  band: number
  count: number
}

export interface Snapshot {
  asOf: number
  phase: Phase
  totals: {
    quota: number
    submitted: number
    decided: number
    eligible: number
    rejected: number
    competition: number
    progress: number | null
    eligibleRate: number | null
    avgProcessingDays: number | null
    firstSelected: number
    finalSelected: number
    /** 담당자용 — 시군 1곳을 선택했을 때만 존재 */
    cutoff: CutoffEstimate | null
  }
  regions: RegionRow[]
  daily: DailyPoint[]
  /** 담당자용 */
  scoreBins: ScoreBin[]
  rejectReasons: RejectReasonItem[]
  demographics: {
    applicants: number
    averageAge: number | null
    ages: AgePoint[]
    gender: CountItem[]
    workTypes: CountItem[]
    insuranceTypes: CountItem[]
    householdSizes: CountItem[]
  }
}

interface Accumulator {
  submitted: number
  waiting: number
  reviewing: number
  eligible: number
  rejected: number
  processingDaysSum: number
  processingCount: number
  firstSelected: number
  finalSelected: number
  finalMinScore: number
  eligibleByScore: number[]
  pendingByScore: number[]
}

function createAccumulator(): Accumulator {
  return {
    submitted: 0,
    waiting: 0,
    reviewing: 0,
    eligible: 0,
    rejected: 0,
    processingDaysSum: 0,
    processingCount: 0,
    firstSelected: 0,
    finalSelected: 0,
    finalMinScore: Number.POSITIVE_INFINITY,
    eligibleByScore: new Array<number>(SCORE_SLOTS).fill(0),
    pendingByScore: new Array<number>(SCORE_SLOTS).fill(0),
  }
}

/**
 * 커트라인 예상: 고득점부터 적합 판정 건은 1명, 미판정 건은 적합률만큼 채워
 * 정원에 도달하는 최저 총점. 2차 검증 이후에는 최종 선정자 최저점(확정).
 */
function estimateCutoff(acc: Accumulator, quota: number, confirmed: boolean, fallbackRate: number): CutoffEstimate {
  if (confirmed) {
    return acc.finalSelected > 0 ? { score: acc.finalMinScore, kind: 'confirmed' } : { score: null, kind: 'none' }
  }
  if (acc.submitted === 0) return { score: null, kind: 'none' }

  const decided = acc.eligible + acc.rejected
  const rate = decided >= MIN_DECIDED_FOR_RATE ? acc.eligible / decided : fallbackRate
  let filled = 0
  let lowest: number | null = null
  for (let slot = SCORE_SLOTS - 1; slot >= 0; slot--) {
    const eligible = acc.eligibleByScore[slot]
    const pending = acc.pendingByScore[slot]
    if (eligible + pending === 0) continue
    lowest = MIN_SCORE + slot
    filled += eligible + pending * rate
    if (filled >= quota) return { score: lowest, kind: 'estimated' }
  }
  return { score: lowest, kind: 'undersubscribed' }
}

function countItems(labels: readonly string[], counts: Map<string, number>): CountItem[] {
  return labels.map((label) => ({ label, count: counts.get(label) ?? 0 }))
}

function increment(map: Map<string, number>, key: string): void {
  map.set(key, (map.get(key) ?? 0) + 1)
}

export function computeSnapshot(dataset: Dataset, asOf: number, region: RegionName | null): Snapshot {
  const { applications, schedule } = dataset
  const confirmed = asOf >= schedule.secondVerificationAt
  const accumulators = new Map<RegionName, Accumulator>(REGIONS.map((profile) => [profile.name, createAccumulator()]))
  const stages = new Array<ReviewStage | null>(applications.length)

  // 1) 시군별 집계 — 필터와 무관하게 항상 전체 시군
  applications.forEach((app, index) => {
    const acc = accumulators.get(app.region)!
    const stage = reviewStageAt(app, schedule, asOf)
    stages[index] = stage
    if (stage === null) return

    acc.submitted++
    acc[stage]++
    const slot = app.score - MIN_SCORE
    if (stage === 'eligible') acc.eligibleByScore[slot]++
    if (stage === 'waiting' || stage === 'reviewing') acc.pendingByScore[slot]++
    if (stage === 'eligible' || stage === 'rejected') {
      acc.processingDaysSum += ((decisionAt(app) ?? asOf) - (app.submittedAt ?? asOf)) / DAY_MS
      acc.processingCount++
    }
    if (app.firstSelected && asOf >= schedule.firstSelectionAt[app.region]) acc.firstSelected++
    if (app.finalSelected && confirmed) {
      acc.finalSelected++
      acc.finalMinScore = Math.min(acc.finalMinScore, app.score)
    }
  })

  let globalEligible = 0
  let globalDecided = 0
  for (const acc of accumulators.values()) {
    globalEligible += acc.eligible
    globalDecided += acc.eligible + acc.rejected
  }
  const fallbackRate = globalDecided >= MIN_DECIDED_FOR_RATE ? globalEligible / globalDecided : DEFAULT_ELIGIBLE_RATE

  const regions: RegionRow[] = REGIONS.map((profile) => {
    const acc = accumulators.get(profile.name)!
    const decided = acc.eligible + acc.rejected
    return {
      name: profile.name,
      quota: profile.quota,
      submitted: acc.submitted,
      waiting: acc.waiting,
      reviewing: acc.reviewing,
      eligible: acc.eligible,
      rejected: acc.rejected,
      competition: acc.submitted / profile.quota,
      progress: acc.submitted ? decided / acc.submitted : 0,
      eligibleRate: decided ? acc.eligible / decided : null,
      avgProcessingDays: acc.processingCount ? acc.processingDaysSum / acc.processingCount : null,
      cutoff: estimateCutoff(acc, profile.quota, confirmed, fallbackRate),
      firstSelected: acc.firstSelected,
      finalSelected: acc.finalSelected,
    }
  })
  const cutoffByRegion = new Map(regions.map((row) => [row.name, row.cutoff]))

  // 2) 필터 범위 집계
  const inScope = (name: RegionName) => region === null || name === region
  const scopedRegions = regions.filter((row) => inScope(row.name))
  const scopedAccumulators = [...accumulators.entries()].filter(([name]) => inScope(name)).map(([, acc]) => acc)
  const sumRows = (pick: (row: RegionRow) => number) => scopedRegions.reduce((sum, row) => sum + pick(row), 0)

  const day0 = startOfDay(schedule.openAt)
  const dayCount = Math.round((startOfDay(schedule.closeAt) - day0) / DAY_MS) + 1
  const dayIndexOf = (ts: number) => Math.min(dayCount - 1, Math.max(0, Math.round((startOfDay(ts) - day0) / DAY_MS)))
  const dailySubmitted = new Array<number>(dayCount).fill(0)

  const scoreBins: ScoreBin[] = Array.from({ length: SCORE_SLOTS }, (_, i) => ({
    score: MIN_SCORE + i,
    withinCutoff: 0,
    outsideCutoff: 0,
    rejected: 0,
  }))
  const reasons = new Map<string, RejectReasonItem>()
  const ageCounts = new Array<number>(MAX_AGE - MIN_AGE + 1).fill(0)
  const genderCounts = new Map<string, number>()
  const workCounts = new Map<string, number>()
  const insuranceCounts = new Map<string, number>()
  const householdCounts = new Map<string, number>()
  let ageSum = 0
  let applicants = 0

  applications.forEach((app, index) => {
    if (!inScope(app.region)) return
    const stage = stages[index]
    if (stage === null || app.submittedAt === null) return

    dailySubmitted[dayIndexOf(app.submittedAt)]++
    applicants++
    ageSum += app.age
    ageCounts[app.age - MIN_AGE]++
    increment(genderCounts, app.gender)
    increment(workCounts, app.workType)
    increment(insuranceCounts, app.insuranceType)
    increment(householdCounts, HOUSEHOLD_LABELS[Math.min(app.householdSize, HOUSEHOLD_LABELS.length) - 1])

    const bin = scoreBins[app.score - MIN_SCORE]
    if (stage === 'rejected') {
      bin.rejected++
      if (app.rejectReason && app.rejectStage) {
        const item = reasons.get(app.rejectReason) ?? { reason: app.rejectReason, stage: app.rejectStage, count: 0 }
        item.count++
        reasons.set(app.rejectReason, item)
      }
      return
    }
    const cutoff = cutoffByRegion.get(app.region)
    if (cutoff?.score != null && app.score >= cutoff.score) bin.withinCutoff++
    else bin.outsideCutoff++
  })

  let cumulativeSubmitted = 0
  const daily: DailyPoint[] = dailySubmitted.map((submitted, i) => {
    const date = addDays(day0, i)
    if (date > asOf) return { date, submitted: null, cumulativeSubmitted: null }
    cumulativeSubmitted += submitted
    return { date, submitted, cumulativeSubmitted }
  })

  const quota = sumRows((row) => row.quota)
  const submitted = sumRows((row) => row.submitted)
  const eligible = sumRows((row) => row.eligible)
  const rejected = sumRows((row) => row.rejected)
  const decided = eligible + rejected
  const processingCount = scopedAccumulators.reduce((sum, acc) => sum + acc.processingCount, 0)
  const processingDaysSum = scopedAccumulators.reduce((sum, acc) => sum + acc.processingDaysSum, 0)

  return {
    asOf,
    phase: phaseAt(schedule, asOf),
    totals: {
      quota,
      submitted,
      decided,
      eligible,
      rejected,
      competition: submitted / quota,
      progress: submitted ? decided / submitted : null,
      eligibleRate: decided ? eligible / decided : null,
      avgProcessingDays: processingCount ? processingDaysSum / processingCount : null,
      firstSelected: sumRows((row) => row.firstSelected),
      finalSelected: sumRows((row) => row.finalSelected),
      cutoff: region === null ? null : (cutoffByRegion.get(region) ?? null),
    },
    regions,
    daily,
    scoreBins,
    rejectReasons: [...reasons.values()].sort((a, b) => b.count - a.count),
    demographics: {
      applicants,
      averageAge: applicants ? ageSum / applicants : null,
      ages: ageCounts.map((count, i) => ({ age: MIN_AGE + i, band: ageBandIndex(MIN_AGE + i), count })),
      gender: countItems(GENDERS, genderCounts),
      workTypes: countItems(WORK_TYPES, workCounts),
      insuranceTypes: countItems(INSURANCE_TYPES, insuranceCounts),
      householdSizes: countItems(HOUSEHOLD_LABELS, householdCounts),
    },
  }
}
