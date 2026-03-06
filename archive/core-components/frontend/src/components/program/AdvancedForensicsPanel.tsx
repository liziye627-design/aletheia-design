import { useMemo, useState } from 'react'
import type { InvestigationRunResult } from '../../api'
import {
  extractClaimTraces,
  extractEvidenceCards,
  extractOpinionSignals,
  extractScoreItems,
} from '../../lib/forensics'
import {
  buildNanoBananaAgentPlan,
  JIMENG_URL,
  NANOBANANA_URL,
} from '../../lib/nanobanana'
import { MermaidCard } from './MermaidCard'

function sanitizeMermaidText(input: string, maxLen = 36) {
  const compact = input.replace(/\s+/g, ' ').trim()
  const limited = compact.length > maxLen ? `${compact.slice(0, maxLen)}…` : compact
  return limited.replace(/["\n\r]/g, '') || '未命名'
}

function safeNodeId(input: string) {
  const cleaned = input.replace(/[^a-zA-Z0-9_]/g, '_')
  return cleaned ? `n_${cleaned}` : `n_${Math.random().toString(36).slice(2, 8)}`
}

export function AdvancedForensicsPanel({ result }: { result: InvestigationRunResult | null }) {
  const [platformFilter, setPlatformFilter] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')

  const evidenceCards = useMemo(() => extractEvidenceCards(result), [result])
  const claimTraces = useMemo(() => extractClaimTraces(result), [result])
  const opinion = useMemo(() => extractOpinionSignals(result), [result])
  const scores = useMemo(() => extractScoreItems(result), [result])
  const claimTracesCount = claimTraces.length
  const strongEvidenceCount = evidenceCards.filter((x) => ['T1', 'T2'].includes(x.tier.toUpperCase())).length
  const reviewQueueCount = Array.isArray((result?.claim_analysis as Record<string, unknown> | undefined)?.review_queue)
    ? (((result?.claim_analysis as Record<string, unknown>).review_queue as unknown[]) || []).length
    : 0

  const platformOptions = useMemo(
    () => ['all', ...Array.from(new Set(evidenceCards.map((e) => e.platform))).slice(0, 12)],
    [evidenceCards]
  )

  const filteredEvidence = useMemo(
    () =>
      evidenceCards.filter((item) => {
        const byPlatform = platformFilter === 'all' || item.platform === platformFilter
        const byTier = tierFilter === 'all' || item.tier.toUpperCase() === tierFilter.toUpperCase()
        return byPlatform && byTier
      }),
    [evidenceCards, platformFilter, tierFilter]
  )

  const scoreMermaid = useMemo(() => {
    if (scores.length === 0) {
      return 'flowchart LR\n  A["暂无评分数据"]'
    }
    const rows = scores.slice(0, 6).map((item) => {
      const value = Number.isFinite(item.score) ? item.score : 0
      return `  "${sanitizeMermaidText(item.label)}" : ${value.toFixed(2)}`
    })
    return ['pie title 评分拆解', ...rows].join('\n')
  }, [scores])

  const evidenceMermaid = useMemo(() => {
    if (claimTraces.length === 0) {
      return 'flowchart LR\n  A["暂无主张或证据"]'
    }

    const evidenceMap = new Map<string, { platform: string; tier: string }>()
    evidenceCards.forEach((card) => {
      if (card.url) {
        evidenceMap.set(card.url, { platform: card.platform, tier: card.tier })
      }
    })

    const lines: string[] = ['flowchart LR']
    const edges: string[] = []

    claimTraces.slice(0, 4).forEach((claim, idx) => {
      const claimId = safeNodeId(`claim_${claim.claimId}_${idx}`)
      const claimLabel = sanitizeMermaidText(`${claim.claimId}: ${claim.text || claim.verdict}`, 32)
      lines.push(`  ${claimId}["${claimLabel}"]`)

      claim.citations.slice(0, 3).forEach((url, eidx) => {
        const meta = evidenceMap.get(url)
        const evidenceId = safeNodeId(`evidence_${idx}_${eidx}`)
        const evidenceLabel = meta
          ? `${sanitizeMermaidText(meta.platform, 10)} ${sanitizeMermaidText(meta.tier, 6)}`
          : '证据'
        lines.push(`  ${evidenceId}["${evidenceLabel}"]`)
        edges.push(`  ${claimId} --> ${evidenceId}`)
      })
    })

    return [...lines, ...edges].join('\n')
  }, [claimTraces, evidenceCards])

  const showNanoBanana = import.meta.env.VITE_NANOBANANA_UI === '1'
  const nanoBananaPlan = useMemo(() => {
    return buildNanoBananaAgentPlan({
      headline: String((result?.search as Record<string, unknown> | undefined)?.keyword || '核查总结'),
      summary: String((result?.claim_analysis as Record<string, unknown> | undefined)?.run_verdict || 'UNCERTAIN'),
      scoreMermaid,
      evidenceMermaid,
      evidenceCount: evidenceCards.length,
      claimCount: claimTraces.length,
      riskLevel: opinion.riskLevel,
    })
  }, [result, scoreMermaid, evidenceMermaid, evidenceCards.length, claimTraces.length, opinion.riskLevel])

  return (
    <div className="advanced-grid">
      <article className="sub-card span-2">
        <div className="sub-head">
          <h4>证据卡与过滤</h4>
          <div className="inline-filters">
            <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)}>
              {platformOptions.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <select value={tierFilter} onChange={(e) => setTierFilter(e.target.value)}>
              <option value="all">all tiers</option>
              <option value="T1">T1</option>
              <option value="T2">T2</option>
              <option value="T3">T3</option>
            </select>
          </div>
        </div>
        <p className="sub-meta">当前筛选后证据：{filteredEvidence.length} 条</p>
        <div className="evidence-list">
          {filteredEvidence.length === 0 && <p className="empty-copy">暂无可展示证据，请先完成一次核查。</p>}
          {filteredEvidence.slice(0, 12).map((item) => (
            <article key={item.id} className="evidence-item">
              <p className="evidence-title">{item.title}</p>
              <p className="evidence-meta">{item.platform} · {item.tier} · {item.publishedAt || '时间未知'}</p>
              <p className="evidence-snippet">{item.snippet || '无摘要'}</p>
              <a href={item.url} target="_blank" rel="noreferrer noopener" className="trace-link">去原文核查</a>
            </article>
          ))}
        </div>
      </article>

      <article className="sub-card">
        <h4>主张追踪</h4>
        <div className="claim-list">
          {claimTraces.length === 0 && <p className="empty-copy">暂无主张追踪数据。</p>}
          {claimTraces.slice(0, 8).map((claim) => (
            <div key={claim.claimId} className="claim-item">
              <p className="claim-title">{claim.claimId} · {claim.verdict}</p>
              <p className="claim-text">{claim.text || '无主张文本'}</p>
              <p className="claim-meta">score {Math.round(claim.score * 100)}% · gate {claim.gatePassed ? 'pass' : 'blocked'}</p>
            </div>
          ))}
        </div>
      </article>

      <article className="sub-card">
        <h4>评论与异常传播</h4>
        <p className="sub-meta">风险：{opinion.riskLevel} · 可疑评论 {Math.round(opinion.suspiciousRatio * 100)}% · 真实评论 {Math.round(opinion.realCommentRatio * 100)}%</p>
        <div className="tag-row">
          {opinion.anomalyTags.length === 0 && <span className="tag">无明显异常标签</span>}
          {opinion.anomalyTags.slice(0, 6).map((tag) => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
        <div className="comment-list">
          {opinion.sampleComments.slice(0, 4).map((comment, idx) => (
            <div key={`${comment.platform}-${idx}`} className="comment-item">
              <p>{comment.text || '空评论'}</p>
              <small>{comment.platform}</small>
            </div>
          ))}
        </div>
      </article>

      <article className="sub-card span-2">
        <h4>评分拆解</h4>
        <div className="score-list">
          {scores.map((item) => {
            const width = Number.isFinite(item.score)
              ? `${Math.max(2, Math.min(100, Math.round(item.score <= 1 ? item.score * 100 : item.score)))}%`
              : '2%'
            return (
              <div key={item.label} className="score-item">
                <div className="score-head">
                  <span>{item.label}</span>
                  <strong>{Number(item.score).toFixed(2)}</strong>
                </div>
                <div className="score-bar">
                  <div className="score-fill" style={{ width }} />
                </div>
              </div>
            )
          })}
        </div>
      </article>

      <MermaidCard
        title="评分拆解图"
        subtitle="Mermaid 可视化"
        definition={scoreMermaid}
      />
      <MermaidCard
        title="证据链路图"
        subtitle="主张 → 证据"
        definition={evidenceMermaid}
      />

      {showNanoBanana && (
        <article className="sub-card span-2 nano-card">
          <div className="sub-head">
            <h4>Nano Banana / 即梦 图像生成（预留）</h4>
            <span className="sub-meta">当前关闭，仅做提示词生成与链接占位</span>
          </div>
          <div className="nano-links">
            {NANOBANANA_URL && <a href={NANOBANANA_URL} target="_blank" rel="noreferrer noopener">Nano Banana 使用</a>}
            {JIMENG_URL && <a href={JIMENG_URL} target="_blank" rel="noreferrer noopener">即梦 使用</a>}
          </div>
          <div className="nano-prompts">
            {nanoBananaPlan.map((task) => (
              <div key={task.id} className="nano-prompt">
                <p>{task.title}</p>
                <pre>{task.prompt}</pre>
              </div>
            ))}
          </div>
        </article>
      )}

      <article className="sub-card span-2">
        <h4>多层次核查价值对比</h4>
        <p className="sub-meta">用于向读者展示：本次结论并非“黑盒回答”，而是可追溯的专家式核查流程。</p>
        <div className="comparison-grid">
          <div className="comparison-col">
            <p className="comparison-title">Aletheia（当前结果）</p>
            <ul className="list-plain compact">
              <li>主张级核验：{claimTracesCount} 条</li>
              <li>T1/T2 强证据：{strongEvidenceCount} 条</li>
              <li>复核队列：{reviewQueueCount} 条</li>
              <li>传播异常：{opinion.riskLevel}</li>
            </ul>
          </div>
          <div className="comparison-col">
            <p className="comparison-title">常见单轮 AI 问答</p>
            <ul className="list-plain compact">
              <li>通常只返回单段结论，缺少阶段日志</li>
              <li>证据链引用少，用户难以逐条核查</li>
              <li>遇到冲突时缺少明确人审门控</li>
              <li>传播风险与异常评论识别能力弱</li>
            </ul>
          </div>
        </div>
      </article>
    </div>
  )
}
