import { FONT_STACK, type ChartTokens } from '../theme'

type Extra = Record<string, unknown>

export function baseOption(tokens: ChartTokens) {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT_STACK, color: tokens.textSecondary },
    animationDuration: 400,
    animationDurationUpdate: 250,
    tooltip: {
      backgroundColor: tokens.surface,
      borderColor: tokens.axis,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: tokens.textPrimary, fontSize: 12, fontFamily: FONT_STACK },
      extraCssText: 'border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,0.14);',
    },
  }
}

export function legendOption(tokens: ChartTokens, extra: Extra = {}) {
  return {
    top: 0,
    left: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 14,
    textStyle: { color: tokens.textSecondary, fontSize: 12 },
    ...extra,
  }
}

export function categoryAxis(tokens: ChartTokens, data: string[], extra: Extra = {}) {
  return {
    type: 'category',
    data,
    axisLine: { lineStyle: { color: tokens.axis } },
    axisTick: { show: false },
    axisLabel: { color: tokens.muted, fontSize: 11, hideOverlap: true },
    ...extra,
  }
}

export function valueAxis(tokens: ChartTokens, extra: Extra = {}) {
  return {
    type: 'value',
    splitLine: { lineStyle: { color: tokens.grid } },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: tokens.muted, fontSize: 11 },
    ...extra,
  }
}

export const HOVER_SHADOW = 'rgba(137, 135, 129, 0.10)'

export function tooltipTitle(text: string): string {
  return `<div style="font-weight:600;margin-bottom:6px">${text}</div>`
}

export function tooltipRow(color: string, label: string, value: string): string {
  return (
    '<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;min-width:180px;line-height:1.7">' +
    `<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:2px;background:${color}"></span>${label}</span>` +
    `<b style="font-variant-numeric:tabular-nums">${value}</b></div>`
  )
}
