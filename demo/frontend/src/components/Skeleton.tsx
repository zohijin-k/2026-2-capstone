import type { CSSProperties, ReactNode } from 'react'
import './skeleton.css'

type SkeletonProps = {
  children: ReactNode
  className?: string
  label?: string
  style?: CSSProperties
}

export function Skeleton({ children, className = '', label = '불러오는 중', style }: SkeletonProps) {
  return (
    <div className={`skeleton ${className}`.trim()} style={style} role="status" aria-busy="true">
      {children}
      <span className="skeleton__sr-only">{label}</span>
    </div>
  )
}

export function SkeletonLine({ width = '100%', className = '' }: { width?: string; className?: string }) {
  return <span className={`skeleton__line ${className}`.trim()} style={{ '--skeleton-width': width } as CSSProperties} aria-hidden="true" />
}

export function SkeletonBlock({ className = '' }: { className?: string }) {
  return <span className={`skeleton__block ${className}`.trim()} aria-hidden="true" />
}

export function SkeletonCard({ children, className = '' }: SkeletonProps) {
  return <div className={`skeleton__card ${className}`.trim()} aria-hidden="true">{children}</div>
}
