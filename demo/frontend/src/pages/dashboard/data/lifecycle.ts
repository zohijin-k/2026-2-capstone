import type { Application, Schedule } from './types'

export type ReviewStage = 'waiting' | 'reviewing' | 'eligible' | 'rejected'

export type Phase = 'before' | 'receiving' | 'reviewing' | 'verifying' | 'finalizing' | 'announced'

export const PHASE_LABEL: Record<Phase, string> = {
  before: '접수 전',
  receiving: '접수 기간',
  reviewing: '시군 1차 심사',
  verifying: '도·허브센터 2차 검증',
  finalizing: '선정 확정 · 발표 준비',
  announced: '선정 결과 발표',
}

/** 서류 단계에서 탈락하면 서류 확인 시점, 그 외에는 자격 심사 완료 시점이 판정 시점 */
export function decisionAt(app: Application): number | null {
  return app.rejectStage === 'document' ? app.docReviewedAt : app.eligibilityReviewedAt
}

export function lastFirstSelectionAt(schedule: Schedule): number {
  return Math.max(...Object.values(schedule.firstSelectionAt))
}

/** 기준 시각의 심사 단계. 아직 제출되지 않은 건은 null */
export function reviewStageAt(app: Application, schedule: Schedule, asOf: number): ReviewStage | null {
  if (app.submittedAt === null || app.submittedAt > asOf) return null
  if (app.docReviewedAt === null || app.docReviewedAt > asOf) return 'waiting'
  if (app.rejectStage === 'document') return 'rejected'
  if (app.eligibilityReviewedAt === null || app.eligibilityReviewedAt > asOf) return 'reviewing'
  if (app.rejectStage === 'eligibility') return 'rejected'
  if (app.rejectStage === 'duplicate' && asOf >= schedule.secondVerificationAt) return 'rejected'
  return 'eligible'
}

export function phaseAt(schedule: Schedule, asOf: number): Phase {
  if (asOf < schedule.openAt) return 'before'
  if (asOf <= schedule.closeAt) return 'receiving'
  if (asOf < lastFirstSelectionAt(schedule)) return 'reviewing'
  if (asOf < schedule.secondVerificationAt) return 'verifying'
  if (asOf < schedule.announcementAt) return 'finalizing'
  return 'announced'
}
