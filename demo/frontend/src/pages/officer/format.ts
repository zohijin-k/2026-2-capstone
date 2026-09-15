/** 담당자 화면이 같이 쓰는 표기 도우미. */

import type { DocStatus } from '../../api.ts'

/**
 * 판정 배지 클래스. 신청자 화면(`index.css`의 `.dstatus`)과 **같은 색**을 쓴다.
 * 같은 판정이 화면마다 다른 색으로 보이면 담당자와 신청자가 다른 결과로 읽는다.
 */
export function badgeClass(status: DocStatus | null): string {
  return `dstatus dstatus--${(status ?? 'needs_review').toLowerCase()}`
}

/** 서류 탭 앞의 상태 점. */
export function dotClass(status: DocStatus | null): string {
  return `tabdot tabdot--${(status ?? 'needs_review').toLowerCase()}`
}

/** 2026-03-05T09:12:00 → 03-05 09:12 */
export function shortTime(value: string | null): string {
  if (!value) return '-'
  return value.slice(5, 16).replace('T', ' ')
}
