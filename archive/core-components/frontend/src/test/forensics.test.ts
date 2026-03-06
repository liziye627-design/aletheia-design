import { describe, expect, it } from 'vitest'
import {
  extractClaimTraces,
  extractEvidenceCards,
  extractOpinionSignals,
  extractScoreItems,
} from '../lib/forensics'

const mockResult = {
  claim_analysis: {
    claims: [
      {
        claim_id: 'c1',
        text: '示例主张',
        verdict: 'LIKELY_FALSE',
        score: 0.2,
        gate_passed: false,
        gate_reasons: ['INSUFFICIENT_EVIDENCE'],
        linked_evidence: [{ url: 'https://example.com/e1' }],
      },
    ],
    claim_reasoning: [
      {
        claim_id: 'c1',
        claim_text: '示例主张',
        citations: [
          {
            url: 'https://example.com/e1',
            platform: 'news',
            tier: 'T1',
            published_at: '2026-03-01T00:00:00Z',
            snippet: '示例证据摘要',
          },
        ],
      },
    ],
  },
  opinion_monitoring: {
    risk_level: 'high',
    suspicious_ratio: 0.45,
    real_comment_ratio: 0.25,
    anomaly_tags: ['BURST_PATTERN'],
    sample_comments: [{ text: '刷屏评论', platform: 'weibo', url: 'https://example.com/c1' }],
  },
  score_breakdown: {
    evidence_score: 0.6,
    conflict_penalty: 0.3,
  },
}

describe('forensics data extraction', () => {
  it('extracts evidence cards', () => {
    const cards = extractEvidenceCards(mockResult as never)
    expect(cards.length).toBe(1)
    expect(cards[0].platform).toBe('news')
  })

  it('extracts claim traces', () => {
    const claims = extractClaimTraces(mockResult as never)
    expect(claims.length).toBe(1)
    expect(claims[0].gatePassed).toBe(false)
  })

  it('extracts opinion signals', () => {
    const opinion = extractOpinionSignals(mockResult as never)
    expect(opinion.riskLevel).toBe('HIGH')
    expect(opinion.sampleComments.length).toBe(1)
  })

  it('extracts score breakdown', () => {
    const scores = extractScoreItems(mockResult as never)
    expect(scores.length).toBe(2)
  })
})
