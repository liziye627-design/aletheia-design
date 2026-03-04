import type { ProgramPhase } from '../../types/runtime'

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

export interface ProgramTimelinePhase {
  key: ProgramPhase
  title: string
  subtitle: string
  status: string
}

export function ProgramTimeline({
  current,
  phases,
  onSelect,
}: {
  current: ProgramPhase
  phases: ProgramTimelinePhase[]
  onSelect: (key: ProgramPhase) => void
}) {
  return (
    <div className="timeline-grid">
      {phases.map((phase) => (
        <button
          key={phase.key}
          type="button"
          onClick={() => onSelect(phase.key)}
          className={cn('timeline-card', current === phase.key && 'is-active', `status-${phase.status}`)}
        >
          <p className="timeline-title">{phase.title}</p>
          <p className="timeline-subtitle">{phase.subtitle}</p>
          <p className="timeline-status">{phase.status}</p>
        </button>
      ))}
    </div>
  )
}
