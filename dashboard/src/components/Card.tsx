import type { ReactNode } from 'react'

interface CardProps {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
  children: ReactNode
}

export function Card({ title, subtitle, actions, className, children }: CardProps) {
  return (
    <section className={className ? `card ${className}` : 'card'}>
      <header className="card-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="card-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="card-actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}
