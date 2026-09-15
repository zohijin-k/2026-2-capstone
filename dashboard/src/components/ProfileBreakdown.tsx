import { fmtInt, fmtPct } from '../lib/format'
import type { CountItem, Snapshot } from '../lib/metrics'
import { Card } from './Card'

const GENDER_COLORS = ['var(--series-1)', 'var(--series-2)']

function BarList({ title, items, total }: { title: string; items: CountItem[]; total: number }) {
  const max = Math.max(1, ...items.map((item) => item.count))
  return (
    <div className="profile-block">
      <h3>{title}</h3>
      <ul className="bar-list">
        {items.map((item) => (
          <li className="bar-row" key={item.label}>
            <span className="bar-label">{item.label}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${(item.count / max) * 100}%` }} />
            </span>
            <span className="bar-value">
              {total ? fmtPct(item.count / total, 1) : '—'}
              <small>{fmtInt(item.count)}명</small>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

interface ProfileBreakdownProps {
  demographics: Snapshot['demographics']
  scopeLabel: string
  className?: string
}

export function ProfileBreakdown({ demographics, scopeLabel, className }: ProfileBreakdownProps) {
  const { applicants, gender } = demographics
  return (
    <Card className={className} title="신청자 특성" subtitle={`${scopeLabel} · 제출 완료 ${fmtInt(applicants)}명`}>
      <div className="profile-grid">
        <div className="profile-block">
          <h3>성별</h3>
          <div className="split-bar" role="img" aria-label={gender.map((g) => `${g.label} ${g.count}명`).join(', ')}>
            {applicants > 0 &&
              gender.map((item, index) => (
                <span key={item.label} style={{ flexGrow: item.count, background: GENDER_COLORS[index] }} />
              ))}
          </div>
          <ul className="split-legend">
            {gender.map((item, index) => (
              <li key={item.label}>
                <i className="swatch" style={{ background: GENDER_COLORS[index] }} />
                {item.label}
                <strong>{applicants ? fmtPct(item.count / applicants, 1) : '—'}</strong>
                <small>{fmtInt(item.count)}명</small>
              </li>
            ))}
          </ul>
        </div>
        <BarList title="근로 유형" items={demographics.workTypes} total={applicants} />
        <BarList title="건강보험 가입 유형" items={demographics.insuranceTypes} total={applicants} />
        <BarList title="가구원 수" items={demographics.householdSizes} total={applicants} />
      </div>
    </Card>
  )
}
