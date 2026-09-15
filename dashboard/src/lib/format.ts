const integerFormat = new Intl.NumberFormat('ko-KR')

export const fmtInt = (value: number): string => integerFormat.format(Math.round(value))

export const fmtPct = (ratio: number, digits = 1): string => `${(ratio * 100).toFixed(digits)}%`

export const fmtRatio = (value: number): string => `${value.toFixed(1)}:1`

export const fmtDays = (value: number): string => `${value.toFixed(1)}일`
