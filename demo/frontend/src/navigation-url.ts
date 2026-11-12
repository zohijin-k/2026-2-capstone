export type Mode = 'applicant' | 'officer'

const NAVIGATION_PARAMS = [
  'mode', 'application', 'stage', 'previous', 'from',
  'o_role', 'o_region', 'o_town', 'o_program', 'o_status', 'o_ai_status',
  'o_submitted_from', 'o_submitted_to', 'o_sort', 'o_page', 'o_page_size',
  'o_open', 'o_slot', 'o_criteria', 'o_criteria_program',
  'role', 'region', 'town', 'program', 'status', 'ai', 'submitted_from',
  'submitted_to', 'sort', 'page', 'page_size', 'slot',
] as const

export function currentParams(): URLSearchParams {
  return new URLSearchParams(window.location.search)
}

export function currentMode(): Mode {
  if (window.location.pathname.startsWith('/officer')) return 'officer'
  if (window.location.pathname.startsWith('/apply')) return 'applicant'
  return currentParams().get('mode') === 'officer' ? 'officer' : 'applicant'
}

export function currentUrl(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`
}

export function routeUrl(path: string, params: Record<string, string | null> = {}, replace = false): void {
  const url = new URL(window.location.href)
  url.pathname = path
  for (const key of NAVIGATION_PARAMS) url.searchParams.delete(key)
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value)
  }
  if (url.href === window.location.href) return
  const method = replace ? 'replaceState' : 'pushState'
  window.history[method](null, '', `${url.pathname}${url.search}${url.hash}`)
}

export function goToHome(): void {
  routeUrl('/')
}
