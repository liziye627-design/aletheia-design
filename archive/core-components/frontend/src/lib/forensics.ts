import type { InvestigationRunResult } from '../api'

export interface EvidenceCard {
  id: string
  title: string
  url: string
  platform: string
  tier: string
  publishedAt: string
  snippet: string
}

export interface ClaimTrace {
  claimId: string
  text: string
  verdict: string
  score: number
  gatePassed: boolean
  gateReasons: string[]
  citations: string[]
}

export interface OpinionSignal {
  riskLevel: string
  suspiciousRatio: number
  realCommentRatio: number
  sampleComments: Array<{ text: string; platform: string; url: string }>
  anomalyTags: string[]
}

export interface ScoreItem {
  label: string
  score: number
}

function safeUrl(v: unknown): string {
  const s = String(v || '').trim()
  return /^https?:\/\//i.test(s) ? s : ''
}

export function extractEvidenceCards(result: InvestigationRunResult | null): EvidenceCard[] {
  if (!result) return []

  const claimAnalysis = (result.claim_analysis || {}) as Record<string, unknown>
  const claimReasoning = Array.isArray(claimAnalysis.claim_reasoning)
    ? (claimAnalysis.claim_reasoning as Array<Record<string, unknown>>)
    : []

  const cards: EvidenceCard[] = []
  for (const row of claimReasoning) {
    const claimId = String(row.claim_id || 'claim')
    const title = String(row.claim_text || row.conclusion_text || '证据引用')
    const citations = Array.isArray(row.citations) ? row.citations : []
    for (let i = 0; i < citations.length; i += 1) {
      const c = (citations[i] || {}) as Record<string, unknown>
      const url = safeUrl(c.url)
      if (!url) continue
      cards.push({
        id: `${claimId}-${i}`,
        title,
        url,
        platform: String(c.platform || c.source || 'unknown'),
        tier: String(c.tier || c.source_tier || 'T2'),
        publishedAt: String(c.published_at || c.time || ''),
        snippet: String(c.snippet || c.note || c.title || ''),
      })
    }
  }

  if (cards.length > 0) return cards

  const sectionBlocks = Array.isArray(result.report_sections)
    ? (result.report_sections as Array<Record<string, unknown>>)
    : []

  for (let i = 0; i < sectionBlocks.length; i += 1) {
    const block = sectionBlocks[i]
    const sources = Array.isArray(block.sources) ? block.sources : []
    for (let j = 0; j < sources.length; j += 1) {
      const s = (sources[j] || {}) as Record<string, unknown>
      const url = safeUrl(s.url)
      if (!url) continue
      cards.push({
        id: `section-${i}-${j}`,
        title: String(block.title || '报告来源'),
        url,
        platform: String(s.platform || s.domain || 'unknown'),
        tier: String(s.tier || 'T2'),
        publishedAt: String(s.published_at || ''),
        snippet: String(s.snippet || s.title || ''),
      })
    }
  }
  return cards
}

export function extractClaimTraces(result: InvestigationRunResult | null): ClaimTrace[] {
  const claimAnalysis = (result?.claim_analysis || {}) as Record<string, unknown>
  const claims = Array.isArray(claimAnalysis.claims)
    ? (claimAnalysis.claims as Array<Record<string, unknown>>)
    : []

  return claims.map((c) => {
    const linkedEvidence = Array.isArray(c.linked_evidence)
      ? (c.linked_evidence as Array<Record<string, unknown>>)
      : []
    const citations = linkedEvidence
      .map((x) => safeUrl((x as Record<string, unknown>).url))
      .filter(Boolean)

    return {
      claimId: String(c.claim_id || 'unknown'),
      text: String(c.text || c.claim_text || ''),
      verdict: String(c.verdict || 'UNCERTAIN').toUpperCase(),
      score: Number(c.score || 0),
      gatePassed: Boolean(c.gate_passed),
      gateReasons: Array.isArray(c.gate_reasons) ? c.gate_reasons.map((x) => String(x)) : [],
      citations,
    }
  })
}

export function extractOpinionSignals(result: InvestigationRunResult | null): OpinionSignal {
  const op = (result?.opinion_monitoring || {}) as Record<string, unknown>
  const sampleComments = Array.isArray(op.sample_comments)
    ? (op.sample_comments as Array<Record<string, unknown>>)
        .slice(0, 8)
        .map((x) => ({
          text: String(x.text || x.content || ''),
          platform: String(x.platform || 'unknown'),
          url: safeUrl(x.url),
        }))
    : []

  return {
    riskLevel: String(op.risk_level || 'unknown').toUpperCase(),
    suspiciousRatio: Number(op.suspicious_ratio || 0),
    realCommentRatio: Number(op.real_comment_ratio || 0),
    sampleComments,
    anomalyTags: Array.isArray(op.anomaly_tags) ? op.anomaly_tags.map((x) => String(x)) : [],
  }
}

export function extractScoreItems(result: InvestigationRunResult | null): ScoreItem[] {
  const split = (result?.score_breakdown || {}) as Record<string, unknown>
  const out: ScoreItem[] = []

  Object.entries(split).forEach(([key, value]) => {
    if (typeof value === 'number') {
      out.push({ label: key, score: value })
    }
  })

  if (out.length > 0) return out

  const acq = (result?.acquisition_report || {}) as Record<string, unknown>
  return [
    { label: 'external_evidence_count', score: Number(acq.external_evidence_count || 0) },
    { label: 'external_primary_count', score: Number(acq.external_primary_count || 0) },
    { label: 'hot_fallback_count', score: Number(acq.hot_fallback_count || 0) },
  ]
}
