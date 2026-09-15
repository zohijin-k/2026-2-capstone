export const HOUR_MS = 3_600_000
export const DAY_MS = 24 * HOUR_MS

export const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const

/** 심사 일정 계산에 쓰는 공휴일 (3~5월만) */
const HOLIDAYS = new Set(['2026-03-02', '2026-05-05', '2026-05-25'])

export function at(year: number, month: number, day: number, hour = 0, minute = 0): number {
  return new Date(year, month - 1, day, hour, minute).getTime()
}

export function startOfDay(ts: number): number {
  const date = new Date(ts)
  date.setHours(0, 0, 0, 0)
  return date.getTime()
}

export function endOfDay(ts: number): number {
  return startOfDay(ts) + DAY_MS - 1
}

export function addDays(ts: number, days: number): number {
  const date = new Date(ts)
  date.setDate(date.getDate() + days)
  return date.getTime()
}

function dateKey(ts: number): string {
  const date = new Date(ts)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function isBusinessDay(ts: number): boolean {
  const weekday = new Date(ts).getDay()
  return weekday !== 0 && weekday !== 6 && !HOLIDAYS.has(dateKey(ts))
}

/** ts가 속한 날부터 영업일 n일 뒤의 자정 */
export function addBusinessDays(ts: number, days: number): number {
  let current = startOfDay(ts)
  let added = 0
  while (added < days) {
    current = addDays(current, 1)
    if (isBusinessDay(current)) added++
  }
  return current
}

/** 3.16(월) */
export function formatDate(ts: number): string {
  const date = new Date(ts)
  return `${date.getMonth() + 1}.${date.getDate()}(${WEEKDAYS[date.getDay()]})`
}

/** 2026. 3. 16.(월) */
export function formatFullDate(ts: number): string {
  const date = new Date(ts)
  return `${date.getFullYear()}. ${date.getMonth() + 1}. ${date.getDate()}.(${WEEKDAYS[date.getDay()]})`
}
