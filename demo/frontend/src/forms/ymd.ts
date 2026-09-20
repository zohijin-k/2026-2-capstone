/** 년·월·일을 따로 받는 날짜 값. */

export interface YMD {
  y: string
  m: string
  d: string
}

export const EMPTY_YMD: YMD = { y: '', m: '', d: '' }

/** YYYY-MM-DD 로 합친다. 한 칸이라도 비어 있으면 빈 문자열. */
export function ymdToISO({ y, m, d }: YMD): string {
  if (!y || !m || !d) return ''
  return `${y.padStart(4, '0')}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
}
