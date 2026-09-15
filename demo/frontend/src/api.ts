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

export interface ApplicationRow {
  id: number
  application_no: string
  program_code: string
  status: string
  form1_json: Record<string, unknown>
  self_check_json: Record<string, string>
  form5_json: Record<string, unknown>
}

export interface SelfCheckResult {
  eligible: boolean
  completed: boolean
  failed_item: number | null
  reason: string
  alternative: string
}

export interface ConsentPayload {
  consent_type: 'privacy' | 'unique_id' | 'third_party' | 'admin_info'
  agreed: boolean
  signature_data_url?: string
  signature_kind?: 'electronic' | 'handwritten'
}

/** 업로드 즉시 판정 결과 한 줄. 사유만 주면 신청자는 또 전화한다 — 해결 방법과 발급처가 함께 온다. */
export interface Finding {
  code: string
  message: string
  how_to_fix: string
  link: string
  severity: 'FAIL' | 'NEEDS_REVIEW'
}

export type DocStatus = 'PASS' | 'FAIL' | 'NEEDS_REVIEW'

export interface UploadedDocument {
  document_id: number
  slot_key: string
  file_name: string
  file_format: string
  expected_doc_type: string | null
  detected_doc_type: string | null
  declared_issue_date: string | null
  status: DocStatus | null
  findings: Finding[]
  extracted: Record<string, string>
  ocr_confidence: number | null
  ocr_tier: string | null
  elapsed_ms: number | null
  page_index: number | null
  uploaded_at: string
}

/** 체크리스트 한 줄. `upload`가 false면 온라인 작성으로 대체된 항목이다. */
export interface DocRequirementRow {
  slot_key: string
  doc_type: string
  label: string
  required: boolean
  upload: boolean
  fulfilled_by: string
  requires_signature: boolean
  check_declared_date: boolean
  min_issue_date: string | null
  issuer: string
  issuer_url: string
  notes: string[]
  warnings: string[]
  alternatives: string[]
  accept: string[]
  documents: UploadedDocument[]
}

export interface DocContext {
  work_category?: string | null
  admin_fixed_term?: boolean
  workplace_count?: number
  handwritten_admin_consent?: boolean
}

export interface Checklist {
  context: DocContext
  work_categories: string[]
  accepted_formats: string[]
  items: DocRequirementRow[]
  upload_total: number
  upload_done: number
  unassigned: UploadedDocument[]
}

export interface MergedUploadResult {
  mode: 'merged'
  source_file: string
  page_count: number
  assigned: UploadedDocument[]
  unassigned: UploadedDocument[]
}

/** 제출을 막는 항목 하나. `goto`는 "어디로 가면 고칠 수 있는가"다. */
export interface Blocker {
  kind: 'form' | 'consent' | 'document' | 'context'
  target: string
  label: string
  message: string
  goto: 'form1' | 'consent' | 'upload'
}

export interface FinalCheck {
  application_no: string
  program_name: string
  allows_supplement: boolean
  supplement_days: number | null
  status: string
  can_submit: boolean
  already_submitted: boolean
  blockers: Blocker[]
  warnings: string[]
  form_summary: { label: string; value: string }[]
  documents: UploadedDocument[]
}

export interface SubmitResult {
  application_no: string
  submitted_at: string | null
  status: string
  message: string
  next_steps: string[]
  notice: string
}

/**
 * 마이페이지 응답.
 *
 * ⚠️ 점수 필드가 없는 것이 사양이다 (공고문: "평가결과는 공개하지 않음").
 * 이 인터페이스에 점수·구간·순위를 추가하면 안 된다.
 */
export interface ApplicationStatus {
  application_no: string
  program_name: string
  status: string
  submitted_at: string | null
  progress: { label: string; state: 'done' | 'current' | 'todo' }[]
  result_notice: string
  documents: UploadedDocument[]
  consents: {
    consent_type: string
    label: string
    agreed: boolean
    agreed_at: string
    signature_kind: string | null
  }[]
  call_center: string
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path} 실패 (${res.status})`)
  return res.json() as Promise<T>
}

/** 파일 업로드는 multipart라 Content-Type을 브라우저가 붙이게 둔다. */
async function form<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(path, { method: 'POST', body })
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `업로드 실패 (${res.status})`)
  }
  return res.json() as Promise<T>
}

export const fetchPrograms = () => json<Program[]>('/api/programs')

export const createApplication = (programCode: string) =>
  json<ApplicationRow>('/api/applications', {
    method: 'POST',
    body: JSON.stringify({ program_code: programCode }),
  })

export const patchApplication = (
  id: number,
  body: { form1?: unknown; self_check?: unknown; form5?: unknown },
) =>
  json<ApplicationRow>(`/api/applications/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const postSelfCheck = (id: number, answers: Record<string, string>) =>
  json<SelfCheckResult>(`/api/applications/${id}/self-check`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  })

export const postConsents = (id: number, consents: ConsentPayload[]) =>
  json<{ saved: unknown[] }>(`/api/applications/${id}/consents`, {
    method: 'POST',
    body: JSON.stringify({ consents }),
  })

export const fetchChecklist = (id: number) =>
  json<Checklist>(`/api/applications/${id}/required-documents`)

/** 근로유형 등을 저장하고 바뀐 체크리스트를 바로 받는다. */
export const putDocContext = (id: number, context: DocContext) =>
  json<Checklist>(`/api/applications/${id}/doc-context`, {
    method: 'PUT',
    body: JSON.stringify({
      work_category: context.work_category ?? null,
      admin_fixed_term: context.admin_fixed_term ?? false,
      workplace_count: context.workplace_count ?? 1,
      handwritten_admin_consent: context.handwritten_admin_consent ?? false,
    }),
  })

export function uploadDocument(
  id: number,
  slotKey: string,
  file: File,
  declaredIssueDate: string,
) {
  const body = new FormData()
  body.append('file', file)
  body.append('slot_key', slotKey)
  if (declaredIssueDate) body.append('declared_issue_date', declaredIssueDate)
  return form<UploadedDocument>(`/api/applications/${id}/documents`, body)
}

/** 여러 서류를 한 파일로 올린 경우. 페이지별로 쪼개 슬롯에 자동 배정한다. */
export function uploadMerged(id: number, file: File) {
  const body = new FormData()
  body.append('file', file)
  body.append('slot_key', 'auto')
  return form<MergedUploadResult>(`/api/applications/${id}/documents`, body)
}

export const deleteDocument = (id: number, documentId: number) =>
  json<{ deleted: string }>(`/api/applications/${id}/documents/${documentId}`, {
    method: 'DELETE',
  })

export const fetchFinalCheck = (id: number) =>
  json<FinalCheck>(`/api/applications/${id}/final-check`)

export const submitApplication = (id: number) =>
  json<SubmitResult>(`/api/applications/${id}/submit`, { method: 'POST' })

export const fetchStatus = (id: number) =>
  json<ApplicationStatus>(`/api/applications/${id}/status`)

/* ------------------------------------------------------------------ 담당자 화면
 *
 * 원본 파일은 `/api/files/{id}`가 `inline`으로만 흘린다. 이 파일 어디에도 파일을
 * 로컬에 저장하는 경로를 만들지 않는다 — 뷰어가 URL을 직접 읽는 것이 전부다 (R4.1).
 */

/** 원본에서 값을 읽어낸 위치. PDF 포인트, **좌상단 원점**이다. */
export interface BBox {
  page: number
  x0: number
  y0: number
  x1: number
  y1: number
}

export type DecisionKey = 'approve' | 'reject' | 'hold'

export interface OfficerAction {
  key: DecisionKey
  /** 버튼 표기. 같은 approve라도 역할마다 뜻이 다르다. */
  label: string
  result_label: string
  tone: 'primary' | 'danger' | 'neutral'
}

export interface OfficerRole {
  key: string
  name: string
  stage: string
  scope: string
  requires_region: boolean
  requires_town: boolean
  /** 정원 대비 몇 %까지 선발하는 단계인가. null이면 선발 권한이 없다. */
  quota_ratio: number | null
  can_bulk: boolean
  notes: string[]
  actions: OfficerAction[]
}

export interface QuotaRow {
  region: string
  quota: number
  applied: number
  selected: number
  limit_120: number
  cutoff_120: number | null
  cutoff_100: number | null
  role_cutoff: number | null
  rate_percent: number
}

export interface OfficerRow {
  application_id: number
  application_no: string
  name: string
  region: string
  town: string
  program_code: string
  program_name: string
  ai_status: DocStatus | null
  ai_status_label: string
  total_score: number | null
  max_total: number | null
  missing_count: number
  submitted_at: string | null
  status: string
  decision: DecisionKey | null
  decision_label: string
  officer_role: string | null
  rank: number | null
}

export interface OfficerListQuery {
  role: string
  region?: string
  town?: string
  program?: string
  status?: string
  ai_status?: string
  submitted_from?: string
  submitted_to?: string
  sort?: string
  page?: number
  page_size?: number
}

export interface OfficerList {
  role: OfficerRole
  scope: {
    region: string
    town: string
    region_locked: boolean
    town_locked: boolean
    regions: string[]
    towns: string[]
  }
  filters: {
    programs: { code: string; name: string }[]
    ai_statuses: { value: string; label: string }[]
    statuses: { value: string; label: string }[]
    sorts: { value: string; label: string }[]
    applied: Record<string, string | null>
  }
  columns: { key: string; label: string }[]
  quota: QuotaRow[]
  total: number
  page: number
  page_size: number
  page_count: number
  rows: OfficerRow[]
}

/** 심사표 한 줄. `bbox`와 `source_file_url`이 좌측 원본 하이라이트의 좌표다 (R4.3). */
export interface ScoreItemRow {
  key: string
  label: string
  score: number
  max_score: number
  band: string
  basis: string
  source_doc: string | null
  source_document_id: number | null
  source_origin: string
  bbox: BBox | null
  incomplete: boolean
  source_slot_key: string | null
  source_file_url: string | null
  source_file_format: string | null
}

export interface ScoreSheetData {
  items: ScoreItemRow[]
  total: number
  max_total: number
  income_percent: number | null
  income_over_limit: boolean
  incomplete: boolean
  tiebreak: number[]
  notes: string[]
}

export interface OfficerDocument {
  document_id: number
  slot_key: string
  label: string
  expected_doc_type: string | null
  detected_doc_type: string | null
  status: DocStatus | null
  findings: Finding[]
  /** 인라인 스트리밍 주소. 뷰어가 이 URL을 그대로 읽는다. */
  file_url: string
  file_name: string
  file_format: string
  page_index: number | null
  extracted: Record<string, string>
  bboxes: Record<string, BBox>
  ocr_confidence: number | null
  ocr_tier: string | null
  declared_issue_date: string | null
  uploaded_at: string
}

export interface ReviewDetailData {
  application_id: number
  application_no: string
  name: string
  program_code: string
  program_name: string
  region: string
  town: string
  status: string
  submitted_at: string | null
  ai: {
    final_status: DocStatus | null
    final_status_label: string
    stage1_status: string | null
    stage2_status: string | null
    recommended_action: string
    reasons: { stage: string; code: string; message: string; doc_type: string | null }[]
  }
  score_sheet: ScoreSheetData
  documents: OfficerDocument[]
  eligibility: { key: string; label: string; ok: boolean; basis: string }[]
  exclusions: { label: string; answer: string; ok: boolean; source: string }[]
  decision: {
    decision: DecisionKey | null
    label: string
    memo: string | null
    officer_role: string | null
    decided_at: string | null
  }
  role: OfficerRole
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  return search.toString()
}

export const fetchOfficerRoles = () => json<OfficerRole[]>('/api/officer/roles')

export const fetchOfficerList = (params: OfficerListQuery) =>
  json<OfficerList>(`/api/officer/applications?${query({ ...params })}`)

export const fetchReviewDetail = (applicationId: number, role: string) =>
  json<ReviewDetailData>(`/api/officer/applications/${applicationId}?${query({ role })}`)

export const postDecision = (
  applicationId: number,
  body: { role: string; decision: DecisionKey; memo: string },
) =>
  json<{ decision: string; label: string; decided_at: string | null }>(
    `/api/officer/applications/${applicationId}/decision`,
    { method: 'POST', body: JSON.stringify(body) },
  )

export const postBulkDecision = (body: {
  role: string
  decision: DecisionKey
  memo: string
  application_ids: number[]
}) =>
  json<{ processed: number }>('/api/officer/applications/decisions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
