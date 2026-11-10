/** 담당자 화면이 같이 쓰는 표기 도우미. */

import type { DocStatus } from '../../api.ts'

/** 서류 탭 앞의 상태 점. */
export function dotClass(status: DocStatus | null): string {
  return `tabdot tabdot--${(status ?? 'needs_review').toLowerCase()}`
}

/** 2026-03-05T09:12:00 → 03-05 09:12 */
export function shortTime(value: string | null): string {
  if (!value) return '-'
  return value.slice(5, 16).replace('T', ' ')
}
