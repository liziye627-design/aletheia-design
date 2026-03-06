import type { InvestigationRunResult } from '../api'
import type { FreshnessState, PhaseStatus, ReviewGateState } from '../types/runtime'

function parseDatetime(value?: unknown): number {
  if (!value || typeof value !== 'string') return 0
  const ts = Date.parse(value)
  return Number.isFinite(ts) ? ts : 0
}

export function deriveFreshness(result: InvestigationRunResult | null, nowMs = Date.now()): FreshnessState {
  const asOf = new Date(nowMs).toISOString()
  const latest = String(result?.latest_related_content_at || result?.earliest_related_content_at || '')
  if (!latest) {
    return { as_of: asOf, latest_evidence_at: undefined, hours_old: undefined, status: 'TIME_UNKNOWN', degraded: true }
  }
  const latestTs = parseDatetime(latest)
  if (!latestTs) {
    return { as_of: asOf, latest_evidence_at: latest, hours_old: undefined, status: 'TIME_UNKNOWN', degraded: true }
  }

  const hoursOld = Math.max(0, (nowMs - latestTs) / (1000 * 60 * 60))
  const stale = hoursOld > 24
  return {
    as_of: asOf,
    latest_evidence_at: latest,
    hours_old: Number(hoursOld.toFixed(1)),
    status: stale ? 'STALE' : 'FRESH',
    degraded: stale,
  }
}

export function deriveReviewGate(result: InvestigationRunResult | null): ReviewGateState {
  const riskFlags = Array.isArray(result?.risk_flags)
    ? result?.risk_flags?.map((x) => String(x).toUpperCase())
    : []
  const claimAnalysis = (result?.claim_analysis || {}) as Record<string, unknown>
  const runVerdict = String(claimAnalysis?.run_verdict || '').toUpperCase()
  const reviewQueue = Array.isArray(claimAnalysis?.review_queue)
    ? (claimAnalysis.review_queue as Array<Record<string, unknown>>)
    : []

  const reasons: string[] = []
  if (runVerdict === 'UNCERTAIN') reasons.push('主张级结论为 UNCERTAIN')
  if (riskFlags.includes('NEEDS_REVIEW')) reasons.push('风险码命中 NEEDS_REVIEW')
  if (riskFlags.includes('INSUFFICIENT_EVIDENCE')) reasons.push('证据不足')
  if (riskFlags.includes('HIGH_RISK_PROPAGATION')) reasons.push('传播异常高风险')
  if (reviewQueue.length > 0) reasons.push(`存在 ${reviewQueue.length} 条复核队列`)

  return {
    required: reasons.length > 0,
    priority: reasons.length >= 3 ? 'high' : reasons.length >= 2 ? 'medium' : 'low',
    reasons,
  }
}

export function prettyReasonCode(code?: string): string {
  const map: Record<string, string> = {
    INSUFFICIENT_EVIDENCE: '证据不足',
    NETWORK_UNREACHABLE: '网络不可达',
    FALLBACK_EMPTY: '平台返回空结果（回退后仍为空）',
    MEDIACRAWLER_LOGIN_REQUIRED: '平台需登录态',
    TIME_BUDGET_EXCEEDED: '超出时间预算',
    AGENT_DEGRADED: '多智能体降级输出',
  }
  const upper = String(code || '').toUpperCase()
  return map[upper] || upper || '未知原因'
}

export function shortConclusion(result: InvestigationRunResult | null): string {
  const status = String(result?.status || '').toLowerCase()
  if (status && !['completed', 'failed', 'error'].includes(status)) {
    return '任务仍在运行中，结论将在完成后更新。'
  }
  const claimAnalysis = (result?.claim_analysis || {}) as Record<string, unknown>
  const verdict = String(claimAnalysis?.run_verdict || result?.status || 'UNCERTAIN').toUpperCase()
  const keyword = String((result?.search as Record<string, unknown> | undefined)?.keyword || '该信息')

  if (verdict === 'VERIFIED' || verdict === 'LIKELY_TRUE') {
    return `“${keyword}”当前基本可信，但仍建议查看证据来源与发布时间。`
  }
  if (verdict === 'LIKELY_FALSE' || verdict === 'FALSE' || verdict === 'FABRICATED') {
    return `“${keyword}”疑点较多，当前不建议直接采信或传播。`
  }
  return `“${keyword}”目前证据不完整，请先核查后再做判断。`
}

export function longConclusion(result: InvestigationRunResult | null, freshnessText: string): string {
  const statusRaw = String(result?.status || '').toLowerCase()
  if (statusRaw && !['completed', 'failed', 'error'].includes(statusRaw)) {
    return '系统正在采集中，请稍候。完成后将给出双层结论与可核查路径。'
  }
  const acquisition = (result?.acquisition_report || {}) as Record<string, unknown>
  const valid = Number(acquisition.external_evidence_count || 0)
  const primary = Number(acquisition.external_primary_count || 0)
  const status = String(result?.status || 'unknown')

  return `系统已完成自动多源核查。当前状态为 ${status}，可用证据 ${valid} 条，其中主证据 ${primary} 条。${freshnessText} 建议优先核查官方或一手来源，再参考二手转述结论。`
}

export function mapStepStatusToPhaseStatus(status: string): PhaseStatus {
  if (status === 'success' || status === 'done' || status === 'completed') return 'done'
  if (status === 'running' || status === 'streaming') return 'running'
  if (status === 'partial') return 'partial'
  if (status === 'failed' || status === 'error') return 'error'
  return 'running'
}
