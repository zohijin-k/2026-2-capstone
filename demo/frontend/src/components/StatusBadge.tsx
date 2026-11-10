import type { DocStatus } from '../api.ts'

type Audience = 'applicant' | 'officer'

export const APPLICANT_DOCUMENT_STATUS = {
  PASS: { label: '확인 완료', icon: '✓' },
  NEEDS_REVIEW: { label: '담당자 확인 예정', icon: '?' },
  FAIL: { label: '다시 올려 주세요', icon: '↻' },
} satisfies Record<DocStatus, { label: string; icon: string }>

const OFFICER_DOCUMENT_STATUS = {
  PASS: { label: '적합', icon: '✓' },
  NEEDS_REVIEW: { label: '확인필요', icon: '?' },
  FAIL: { label: '부적합', icon: '!' },
} satisfies Record<DocStatus, { label: string; icon: string }>

export default function StatusBadge({
  status,
  audience,
  compact = false,
}: {
  status: DocStatus
  audience: Audience
  compact?: boolean
}) {
  const presentation = audience === 'applicant'
    ? APPLICANT_DOCUMENT_STATUS[status]
    : OFFICER_DOCUMENT_STATUS[status]
  return (
    <span className={`status-badge status-badge--${status.toLowerCase()}${compact ? ' status-badge--compact' : ''}`} role="status">
      <span className="status-badge__icon" aria-hidden="true">{presentation.icon}</span>
      <span>{presentation.label}</span>
    </span>
  )
}
