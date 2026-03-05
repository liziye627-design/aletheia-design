import { describe, expect, it } from 'vitest'
import {
  deriveFreshness,
  deriveReviewGate,
  mapStepStatusToPhaseStatus,
  prettyReasonCode,
} from '../lib/programRuntime'
import { mapStepIdToPhase } from '../store/programStore'

describe('program runtime helpers', () => {
  it('maps step id to expected phase', () => {
    expect(mapStepIdToPhase('intent_preview')).toBe('preview')
    expect(mapStepIdToPhase('multiplatform_search')).toBe('evidence')
    expect(mapStepIdToPhase('claim_analysis')).toBe('verification')
    expect(mapStepIdToPhase('unknown_step')).toBe('conclusion')
  })

  it('derives stale freshness correctly', () => {
    const now = Date.parse('2026-03-01T12:00:00.000Z')
    const result = {
      latest_related_content_at: '2026-02-28T00:00:00.000Z',
    } as Record<string, unknown>

    const freshness = deriveFreshness(result as never, now)
    expect(freshness.status).toBe('STALE')
    expect(freshness.degraded).toBe(true)
    expect(freshness.hours_old).toBeGreaterThan(24)
  })

  it('derives review gate when uncertain and flags exist', () => {
    const result = {
      risk_flags: ['NEEDS_REVIEW', 'INSUFFICIENT_EVIDENCE'],
      claim_analysis: {
        run_verdict: 'UNCERTAIN',
        review_queue: [{ claim_id: 'c1' }],
      },
    } as Record<string, unknown>

    const gate = deriveReviewGate(result as never)
    expect(gate.required).toBe(true)
    expect(gate.priority).toBe('high')
    expect(gate.reasons.length).toBeGreaterThanOrEqual(3)
  })

  it('maps reason code and stream statuses', () => {
    expect(prettyReasonCode('INSUFFICIENT_EVIDENCE')).toBe('证据不足')
    expect(mapStepStatusToPhaseStatus('success')).toBe('done')
    expect(mapStepStatusToPhaseStatus('failed')).toBe('error')
  })
})
