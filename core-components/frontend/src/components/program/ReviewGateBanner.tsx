import type { ReviewGateState } from '../../types/runtime'

export function ReviewGateBanner({ gate }: { gate: ReviewGateState }) {
  if (!gate.required) return null

  return (
    <section className="review-banner">
      <strong>需人工复核</strong>
      <p>优先级：{gate.priority.toUpperCase()}。{gate.reasons.join('；')}</p>
    </section>
  )
}
