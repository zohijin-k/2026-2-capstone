/** 백엔드 호출. vite dev 서버가 /api 를 :8000 으로 프록시한다. */

import {
  MOCK_ROLES,
  isMockId,
  mockDecide,
  mockOfficerList,
  mockReviewDetail,
} from './pages/officer/mock-data.ts'

/**
 * 사업 설정. 화면 분기는 전부 이 값으로 한다.
 *
 * 컴포넌트 안에서 `code === 'job_package'` 같은 비교를 하지 않는 것이 규칙이다.
 * 두 사업의 차이(선발 방식·보완 정책·연령 기준·소득요건·지원 항목)는 서버가
 * 이 구조체 하나로 알려준다.
 */
export interface Program {
  code: string
  name: string
  announcement_date: string
  document_cutoff: string
  age_basis_date: string
  birth_range: [string, string]
  selection: 'scored' | 'first_come'
  is_first_come: boolean
  supplement_days: number | null
  allows_supplement: boolean
  has_income_requirement: boolean
  has_work_requirement: boolean
  has_subsidy_items: boolean
  apply_period: [string, string]
  /** 2차 모집이 있는 사업의 2차 신청 기간. 없으면 null. */
  apply_period_2: [string, string] | null
  quota_by_region: Record<string, number> | null
  quota_total: number | null
  /** 자가진단 문항 번호. 두배적금 8문항 / 취업패키지 2문항. */
  self_check_items: number[]
  /** 지원 항목표. 항목이 없는 사업은 null. */
  subsidy_catalog: SubsidyCatalogItem[] | null
  site_url: string
  call_center: string
  notes: string[]
  /** 공고문 전문을 카드에 펼칠 사업만 채워진다. null이면 요약 행만 그린다. */
  detail: ProgramDetail | null
  /** 사업계획서 구조로 카드를 펼칠 사업만 채워진다. */
  package_detail: PackageDetail | null
}

/** 신청서류 표의 「항목별 추가서류」 한 행. */
export interface DocRow {
  item: string
  docs: string[]
}

/** 서류심사 절차 한 단계. */
export interface ReviewStep {
  title: string
  points: string[]
}

/**
 * 사업계획서 「Ⅲ. 세부사업계획」 1~3절(사업신청·서류심사·지원금 지급).
 *
 * 금액·횟수·지원 항목은 여기 없다. 그 값은 `subsidy_catalog`가 유일한 출처다.
 * 필드 의미는 백엔드 `PackageDetail` 참조.
 */
export interface PackageDetail {
  early_close_note: string
  target_points: string[]
  apply_method: string
  apply_items_note: string
  common_docs: string[]
  item_docs: DocRow[]
  doc_cutoff_notice: string
  review_steps: ReviewStep[]
  supplement_notes: string[]
  payment_methods: string[]
}

/** 적금 구조 한 행. 청년이 얼마를 넣으면 지자체가 얼마를 얹는지. */
export interface SavingsPlan {
  monthly_self: number
  monthly_grant: number
  months: number
  maturity_label: string
  note: string
}

/** 신청 절차 한 단계. `url`이 비어 있지 않으면 label 전체를 링크로 건다. */
export interface ApplyStep {
  label: string
  url: string
}

/** 사업 선택 카드에 펼치는 공고문 상세. 필드 의미는 백엔드 `ProgramDetail` 참조. */
export interface ProgramDetail {
  target_summary: string
  target_points: string[]
  benefit_summary: string
  savings_plan: SavingsPlan | null
  announce_period: [string, string]
  apply_open_time: string
  apply_close_time: string
  apply_method: string
  apply_steps: ApplyStep[]
  deadline_warning: string
  cautions: string[]
  missing_doc_examples: string[]
  selection_methods: string[]
}

/** 취업지원패키지 지원 항목 1종 (사업계획서 「지원내용」 표). */
export interface SubsidyCatalogItem {
  item_type: string
  label: string
  description: string
  unit_cap: number
  max_count: number
  /** true면 실비(영수증 금액과 한도 중 작은 값), false면 정액. */
  actual_cost: boolean
  needs_receipt: boolean
  max_amount: number
  note: string
  amount_label: string
  count_label: string
  extra_docs: string[]
  performance_target: number | null
}

export interface SubsidySelection {
  item_type: string
  count: number
  receipts: (number | null)[]
}

/** 지급 계산 한 줄. `calculation`이 "왜 이 금액인가"의 답이다. */
export interface SubsidyLine {
  item_type: string
  label: string
  index: number
  unit_cap: number
  actual_cost: boolean
  receipt_amount: number | null
  granted_amount: number
  calculation: string
  pending: boolean
}

export interface SubsidyEstimate {
  lines: SubsidyLine[]
  total_granted: number
  warnings: string[]
  pending: boolean
}

export interface SubsidyState {
  program_code: string
  program_name: string
  catalog: SubsidyCatalogItem[]
  selections: SubsidySelection[]
  estimate: SubsidyEstimate
  notice: string
}

/** 선착순 접수 순번 (R6). 점수제 사업에서는 null. */
export interface FirstComeInfo {
  enabled: boolean
  position: number
  quota: number | null
  remaining: number | null
  submitted: boolean
  notice: string
}

/** 서류 보완 기한 (E12). 보완이 없는 사업에서는 null. */
export interface SupplementInfo {
  days: number | null
  deadline: string
  days_left: number
  hours_left: number
  expired: boolean
  targets: { label: string; reason: string }[]
  notice: string
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
  /** 이번 사업에서 물은 문항 수. 두배적금 8 / 취업패키지 2. */
  total_items: number
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
  /** 이 자리에 인정되는 서류들. 응시확인서 **또는** 성적표처럼 택1인 칸이 있다. */
  doc_type_choices: string[]
  /** 서류에 반드시 찍혀 있어야 하는 항목 (예: 응시확인서의 "응시일"). */
  required_fields: string[]
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

/** 업로드 화면이 사업 코드로 분기하지 않도록 서버가 내려주는 안내. */
export interface ChecklistProgram {
  code: string
  name: string
  selection: 'scored' | 'first_come'
  allows_supplement: boolean
  supplement_days: number | null
  document_cutoff: string
  asks_work_category: boolean
  has_subsidy_items: boolean
}

export interface Checklist {
  context: DocContext
  program: ChecklistProgram
  work_categories: string[]
  accepted_formats: string[]
  items: DocRequirementRow[]
  upload_total: number
  upload_done: number
  unassigned: UploadedDocument[]
  /** 판정 컷라인 등 TF 미확정 가정값 안내. `(데모 추정치)` 라벨이 붙어 온다. */
  assumption_notes: string[]
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
  kind: 'form' | 'consent' | 'document' | 'context' | 'subsidy'
  target: string
  label: string
  message: string
  goto: 'form1' | 'consent' | 'upload' | 'subsidy'
}

export interface FinalCheck {
  application_no: string
  program_code: string
  program_name: string
  allows_supplement: boolean
  supplement_days: number | null
  selection: 'scored' | 'first_come'
  first_come: FirstComeInfo | null
  subsidy: SubsidyEstimate | null
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
  first_come: FirstComeInfo | null
  supplement: SupplementInfo | null
  subsidy: SubsidyEstimate | null
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
  program_code: string
  program_name: string
  status: string
  submitted_at: string | null
  progress: { label: string; state: 'done' | 'current' | 'todo' }[]
  result_notice: string
  first_come: FirstComeInfo | null
  supplement: SupplementInfo | null
  subsidy: SubsidyEstimate | null
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

/** 취업지원패키지 지원 항목 — 저장된 선택과 예상 지원금. */
export const fetchSubsidyItems = (id: number) =>
  json<SubsidyState>(`/api/applications/${id}/subsidy-items`)

/** 고른 항목을 통째로 저장하고, 다시 계산된 지급액을 받는다. */
export const saveSubsidyItems = (id: number, items: SubsidySelection[]) =>
  json<SubsidyState>(`/api/applications/${id}/subsidy-items`, {
    method: 'POST',
    body: JSON.stringify({ items }),
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
  /** 선착순 사업을 고른 경우의 접수 진행률. 점수제 사업에서는 null. */
  first_come: {
    program_code: string
    program_name: string
    quota: number
    applied: number
    selected: number
    remaining: number
    rate_percent: number
    supplement_days: number | null
    notice: string
  } | null
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

/** 작성 서식 한 장 (P7 / R9). 업로드 서류와 같은 뷰어에서 인라인으로 연다. */
export interface FormExport {
  form_no: string
  title: string
  label: string
  /** 인라인 스트리밍 주소. 저장 링크가 아니다. */
  file_url: string
  file_name: string
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
  /** 선발 방식. 선착순 사업에는 심사표가 없다. */
  selection: 'scored' | 'first_come'
  /** 취업패키지 항목별 지급 내역. 점수제 사업에서는 null. */
  subsidy: SubsidyEstimate | null
  /** 7일 보완 기한. 보완이 없는 사업이거나 보완 대상이 아니면 null. */
  supplement: SupplementInfo | null
  documents: OfficerDocument[]
  /** 신청자가 작성한 서식을 원본 서식 모양 그대로 내보낸 PDF. 없으면 빈 배열. */
  forms: FormExport[]
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

// ---------------------------------------------------------------- 담당자 목업

/**
 * 담당자 화면 목업 전환 (`pages/officer/mock-data.ts`).
 *
 * 켜지는 조건은 둘이다.
 *
 *   - `?mock=1` — 강제로 켠다. 백엔드가 떠 있어도 목업을 본다.
 *   - 자동 — 담당자 목록 API가 실패했거나 **접수 건이 0건**일 때. 빈 표를 띄우고
 *     "데이터가 없습니다"로 시연이 끊기는 것보다, 예시로 채운 화면을 보여주고
 *     목업임을 상단에 밝히는 편이 낫다.
 *
 * `?mock=0`을 붙이면 어떤 경우에도 목업을 쓰지 않는다 — 실제 접수 건이 0건인 것을
 * 확인해야 할 때 쓴다.
 */
const MOCK_PARAM = new URLSearchParams(window.location.search).get('mock')
const MOCK_FORCED = MOCK_PARAM === '1' || MOCK_PARAM === 'on'
const MOCK_BLOCKED = MOCK_PARAM === '0' || MOCK_PARAM === 'off'

let mockActive = MOCK_FORCED

/** 지금 담당자 화면이 목업을 보고 있는가. 화면 상단 배너가 이 값을 읽는다. */
export const isOfficerMockActive = () => mockActive

export const fetchOfficerRoles = async (): Promise<OfficerRole[]> => {
  if (mockActive) return MOCK_ROLES
  try {
    return await json<OfficerRole[]>('/api/officer/roles')
  } catch (e) {
    if (MOCK_BLOCKED) throw e
    mockActive = true
    return MOCK_ROLES
  }
}

export const fetchOfficerList = async (params: OfficerListQuery): Promise<OfficerList> => {
  if (mockActive) return mockOfficerList(params)
  try {
    const body = await json<OfficerList>(`/api/officer/applications?${query({ ...params })}`)
    // 필터를 걸어 0건인 것과 접수 자체가 0건인 것은 다르다. 후자일 때만 목업으로 넘어간다.
    const unfiltered =
      !params.program && !params.status && !params.ai_status && !params.submitted_from && !params.submitted_to
    if (body.total === 0 && unfiltered && !MOCK_BLOCKED) {
      mockActive = true
      return mockOfficerList(params)
    }
    return body
  } catch (e) {
    if (MOCK_BLOCKED) throw e
    mockActive = true
    return mockOfficerList(params)
  }
}

export const fetchReviewDetail = (applicationId: number, role: string) =>
  mockActive || isMockId(applicationId)
    ? Promise.resolve(mockReviewDetail(applicationId, role))
    : json<ReviewDetailData>(`/api/officer/applications/${applicationId}?${query({ role })}`)

export const postDecision = (
  applicationId: number,
  body: { role: string; decision: DecisionKey; memo: string },
) => {
  if (mockActive || isMockId(applicationId)) {
    mockDecide([applicationId], body.role, body.decision, body.memo)
    const detail = mockReviewDetail(applicationId, body.role)
    return Promise.resolve({
      decision: body.decision,
      label: detail.decision.label,
      decided_at: detail.decision.decided_at,
    })
  }
  return json<{ decision: string; label: string; decided_at: string | null }>(
    `/api/officer/applications/${applicationId}/decision`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export const postBulkDecision = (body: {
  role: string
  decision: DecisionKey
  memo: string
  application_ids: number[]
}) => {
  if (mockActive) {
    return Promise.resolve({
      processed: mockDecide(body.application_ids, body.role, body.decision, body.memo),
    })
  }
  return json<{ processed: number }>('/api/officer/applications/decisions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
