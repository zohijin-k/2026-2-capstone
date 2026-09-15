export type ThemeMode = 'light' | 'dark'

export interface ChartTokens {
  surface: string
  textPrimary: string
  textSecondary: string
  muted: string
  grid: string
  axis: string
  /** 범주 색상 슬롯 1~3 (고정 순서, 검증된 조합) */
  series1: string
  series2: string
  series3: string
  /** 대기·기타처럼 의미가 약한 구간 */
  neutral: string
  /** 순서형(연령대 등) 단일 색상 램프, 낮음→높음 */
  ordinal: [string, string, string, string]
  /** 연속값(지도) 단일 색상 램프, 낮음→높음 */
  sequential: string[]
}

export const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif'

export const TOKENS: Record<ThemeMode, ChartTokens> = {
  light: {
    surface: '#fcfcfb',
    textPrimary: '#0b0b0b',
    textSecondary: '#52514e',
    muted: '#898781',
    grid: '#e1e0d9',
    axis: '#c3c2b7',
    series1: '#2a78d6',
    series2: '#eb6834',
    series3: '#1baf7a',
    neutral: '#c3c2b7',
    ordinal: ['#86b6ef', '#3987e5', '#256abf', '#184f95'],
    sequential: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'],
  },
  dark: {
    surface: '#1a1a19',
    textPrimary: '#ffffff',
    textSecondary: '#c3c2b7',
    muted: '#898781',
    grid: '#2c2c2a',
    axis: '#383835',
    series1: '#3987e5',
    series2: '#d95926',
    series3: '#199e70',
    neutral: '#52514e',
    ordinal: ['#184f95', '#256abf', '#3987e5', '#86b6ef'],
    sequential: ['#184f95', '#1c5cab', '#256abf', '#2a78d6', '#5598e7', '#86b6ef', '#b7d3f6'],
  },
}
