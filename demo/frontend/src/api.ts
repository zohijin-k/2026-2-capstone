/** 백엔드 호출. vite dev 서버가 /api 를 :8000 으로 프록시한다. */

export interface Program {
  code: string
  name: string
  announcement_date: string
  document_cutoff: string
  age_basis_date: string
  birth_range: [string, string]
  selection: 'scored' | 'first_come'
  supplement_days: number | null
  allows_supplement: boolean
  has_income_requirement: boolean
  apply_period: [string, string]
  quota_by_region: Record<string, number> | null
  quota_total: number | null
  site_url: string
  call_center: string
  notes: string[]
}

export async function fetchPrograms(): Promise<Program[]> {
  const res = await fetch('/api/programs')
  if (!res.ok) throw new Error(`사업 목록을 불러오지 못했습니다 (${res.status})`)
  return res.json()
}
