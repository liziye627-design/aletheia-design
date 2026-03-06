import type { ReactNode } from 'react'

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

export function ProgramStageCard({
  title,
  status,
  summary,
  actionHint,
  children,
  collapsible = false,
  isOpen = true,
  onToggle,
}: {
  title: string
  status: string
  summary: string
  actionHint: string
  children?: ReactNode
  collapsible?: boolean
  isOpen?: boolean
  onToggle?: () => void
}) {
  return (
    <article className={cn('stage-card', collapsible && 'is-collapsible')}>
      <div className="stage-head">
        <div>
          <h3>{title}</h3>
          <p className="stage-summary">{summary || '系统正在处理中...'}</p>
        </div>
        <div className="stage-actions">
          <span className={cn('status-pill', `status-${status}`)}>{status}</span>
          {collapsible && (
            <button type="button" className="stage-toggle" onClick={onToggle}>
              {isOpen ? '收起' : '展开'}
            </button>
          )}
        </div>
      </div>
      <p className="stage-action">关键动作：{actionHint}</p>
      {(!collapsible || isOpen) && children}
    </article>
  )
}
