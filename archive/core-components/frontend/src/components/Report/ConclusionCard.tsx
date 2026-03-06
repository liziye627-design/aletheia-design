/**
 * 结论卡片组件 - 通俗化、可验证、有传播性
 *
 * 设计理念：
 * 1. 结论通俗化 - 双层结论：短句传播 + 解释段
 * 2. 验证链路可见 - 可核查动作，不只是链接
 * 3. 时效性透明 - 标注截至时间，过时自动降级
 * 4. 人审门控 - 中高风险强制触发人工复核
 */

import { useState } from 'react'
import type { VerificationRunState } from '../../types/runtime'
import { Badge, Card } from '../common'

interface ConclusionCardProps {
  run: VerificationRunState | null
  isRunning: boolean
}

// 可信度等级的通俗化表达
const TRUST_LABELS: Record<string, { label: string; emoji: string; color: string; action: string }> = {
  VERIFIED: { label: '基本可信', emoji: '✓', color: 'emerald', action: '可作为参考依据，但仍建议保持审慎' },
  LIKELY_TRUE: { label: '有一定证据', emoji: '○', color: 'cyan', action: '建议关注后续进展，等待更多权威确认' },
  UNCERTAIN: { label: '无法判断', emoji: '?', color: 'amber', action: '证据不足或存在矛盾，建议进一步核实' },
  LIKELY_FALSE: { label: '可能不实', emoji: '△', color: 'orange', action: '多处疑点，不建议采信或传播' },
  FABRICATED: { label: '已证实虚假', emoji: '✗', color: 'red', action: '已被权威辟谣，请勿传播' },
}

// 空结果原因码的通俗化表达
const NO_DATA_REASONS: Record<string, { label: string; action: string }> = {
  FALLBACK_EMPTY: { label: '所有平台均未返回结果', action: '建议调整关键词或检查网络' },
  NETWORK_UNREACHABLE: { label: '网络连接失败', action: '请检查网络环境或稍后重试' },
  MEDIACRAWLER_LOGIN_REQUIRED: { label: '需要登录才能访问', action: '该平台需要登录态，请联系管理员配置' },
  INSUFFICIENT_EVIDENCE: { label: '证据不足', action: '建议补充更多关键词进行检索' },
  TIMEOUT: { label: '检索超时', action: '平台响应较慢，建议稍后重试' },
}

// 从 generated_article 中提取结构化数据
function extractArticleData(run: VerificationRunState | null) {
  const article = run?.multiAgent?.generated_article
  if (!article) return null

  if (typeof article === 'string') {
    return { body_markdown: article }
  }

  return {
    title: article.title,
    lead: article.lead,
    body_markdown: article.body_markdown,
    highlights: article.highlights ?? [],
    insufficient_evidence: article.insufficient_evidence ?? [],
    public_verdict: article.public_verdict,
    reader_checklist: article.reader_checklist,
    evidence_boundary: article.evidence_boundary,
    freshness: article.freshness,
    human_review: article.human_review,
  }
}

// 生成默认的双层结论
function buildDefaultVerdict(run: VerificationRunState | null) {
  if (!run) return null

  const score = run.analysis?.reasoning_chain.final_score ?? run.multiAgent?.overall_credibility ?? 0
  const keyword = run.keyword || '该内容'
  const sources = run.search?.platform_count ?? 0
  const posts = run.search?.total_posts ?? 0

  let label: string
  let headline: string
  let explain: string

  if (score >= 0.75) {
    label = 'VERIFIED'
    headline = `经多方核实，「${keyword}」基本可信`
    explain = `跨 ${sources} 个平台检索到 ${posts} 条信息，多个权威信源报道一致。`
  } else if (score >= 0.5) {
    label = 'LIKELY_TRUE'
    headline = `「${keyword}」有一定证据支持`
    explain = `部分信源支持该说法，但证据覆盖或时效性存在不足。`
  } else if (score >= 0.35) {
    label = 'UNCERTAIN'
    headline = `「${keyword}」目前证据不足`
    explain = `现有证据存在矛盾或缺失，无法做出明确判断。`
  } else if (score >= 0.2) {
    label = 'LIKELY_FALSE'
    headline = `「${keyword}」存在多处疑点`
    explain = `多个维度检测到异常或矛盾，建议谨慎对待。`
  } else {
    label = 'FABRICATED'
    headline = `「${keyword}」已被证实为虚假`
    explain = `权威信源已辟谣或证据确凿证明其不实。`
  }

  return {
    headline,
    explain,
    label: label as keyof typeof TRUST_LABELS,
    confidence: score,
    as_of: new Date().toISOString(),
  }
}

export function ConclusionCard({ run, isRunning }: ConclusionCardProps) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null)

  if (!run) {
    return (
      <Card className="border-slate-700/80 bg-slate-900/70 p-6">
        <p className="text-slate-400">等待核验任务启动...</p>
      </Card>
    )
  }

  const articleData = extractArticleData(run)
  const verdict = articleData?.public_verdict ?? buildDefaultVerdict(run)
  const readerChecklist = articleData?.reader_checklist ?? []
  const evidenceBoundary = articleData?.evidence_boundary
  const freshness = articleData?.freshness
  const humanReview = articleData?.human_review
  const noDataExplainer = run.multiAgent?.no_data_explainer

  const trustInfo = verdict ? TRUST_LABELS[verdict.label] ?? TRUST_LABELS.UNCERTAIN : TRUST_LABELS.UNCERTAIN
  const finalScore = verdict?.confidence ?? run.multiAgent?.overall_credibility ?? 0

  // 检查是否需要显示空结果解释
  const showNoDataExplainer = noDataExplainer && (run.search?.total_posts ?? 0) === 0

  return (
    <div className="space-y-4">
      {/* 核心结论卡片 - 双层结论 */}
      <Card className={`border-${trustInfo.color}-500/40 bg-${trustInfo.color}-500/10`}>
        <div className="flex items-start gap-4">
          <div className={`flex h-12 w-12 items-center justify-center rounded-full bg-${trustInfo.color}-500/20 text-2xl shrink-0`}>
            {trustInfo.emoji}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={trustInfo.color === 'emerald' ? 'success' : trustInfo.color === 'red' ? 'danger' : 'warning'}>
                {trustInfo.label}
              </Badge>
              <Badge variant="default">{Math.round(finalScore * 100)}% 可信度</Badge>
              {freshness && (
                <Badge variant={freshness.status === 'FRESH' ? 'success' : freshness.status === 'STALE' ? 'warning' : 'default'}>
                  时效：{freshness.status === 'FRESH' ? '新鲜' : freshness.status === 'STALE' ? '过时' : '未知'}
                </Badge>
              )}
            </div>

            {/* 短结论（30-45字） */}
            <p className="mt-3 text-lg font-medium text-slate-100 leading-snug">
              {verdict?.headline ?? '正在分析中...'}
            </p>

            {/* 解释段（90-130字） */}
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              {verdict?.explain ?? trustInfo.action}
            </p>

            {/* 截至时间 */}
            {freshness?.as_of && (
              <p className="mt-2 text-xs text-slate-500">
                截至 {new Date(freshness.as_of).toLocaleString('zh-CN')}
                {freshness.hours_old !== undefined && freshness.hours_old !== null && (
                  <span className="ml-2">（证据距今 {freshness.hours_old.toFixed(1)} 小时）</span>
                )}
              </p>
            )}

            {/* 时效性降级警告 */}
            {freshness?.degraded && (
              <p className="mt-2 text-xs text-amber-300">
                ⚠️ 证据时效性不足，结论可能已过时，建议补充最新信息
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* 一句话分享版 */}
      <Card className="border-slate-700/80 bg-slate-900/70">
        <p className="text-xs text-slate-500 mb-2">一句话分享版（可直接复制传播）</p>
        <p className="text-slate-200 font-medium leading-relaxed">
          「{verdict?.headline ?? '分析中'}」——Aletheia 核验于 {new Date().toLocaleDateString('zh-CN')}
        </p>
      </Card>

      {/* 可核查动作卡片 */}
      {readerChecklist.length > 0 && (
        <Card className="border-slate-700/80 bg-slate-900/70">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300 mb-3">
            🔍 你可以如何验证
          </h3>
          <div className="space-y-3">
            {readerChecklist.slice(0, 5).map((item, idx) => (
              <div key={idx} className="rounded-lg border border-slate-700 bg-slate-950/50 p-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-slate-200">{item.claim_point}</span>
                  <Badge variant={item.status === 'SUPPORTED' ? 'success' : item.status === 'REFUTED' ? 'danger' : 'warning'}>
                    {item.status === 'SUPPORTED' ? '已验证' : item.status === 'REFUTED' ? '已证伪' : '待核实'}
                  </Badge>
                </div>
                <p className="mt-2 text-xs text-cyan-300 leading-relaxed">
                  👉 {item.how_to_check}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  去查：<span className="text-slate-300">{item.source_hint}</span>
                </p>
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 text-xs text-cyan-400 underline block"
                  >
                    查看原始链接 →
                  </a>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 证据边界 */}
      {evidenceBoundary && (
        <Card className="border-slate-700/80 bg-slate-900/70">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300 mb-3">
            📋 证据边界说明
          </h3>
          <div className="space-y-3 text-xs">
            {evidenceBoundary.well_supported.length > 0 && (
              <div>
                <p className="font-medium text-emerald-300 mb-1">✓ 有充分证据</p>
                <ul className="space-y-1 text-slate-300">
                  {evidenceBoundary.well_supported.slice(0, 3).map((item, idx) => (
                    <li key={idx}>• {item}</li>
                  ))}
                </ul>
              </div>
            )}
            {evidenceBoundary.insufficient.length > 0 && (
              <div>
                <p className="font-medium text-amber-300 mb-1">⚠️ 证据不足</p>
                <ul className="space-y-1 text-slate-300">
                  {evidenceBoundary.insufficient.slice(0, 3).map((item, idx) => (
                    <li key={idx}>• {item}</li>
                  ))}
                </ul>
              </div>
            )}
            {evidenceBoundary.conflicting.length > 0 && (
              <div>
                <p className="font-medium text-red-300 mb-1">✗ 存在矛盾</p>
                <ul className="space-y-1 text-slate-300">
                  {evidenceBoundary.conflicting.slice(0, 3).map((item, idx) => (
                    <li key={idx}>• {item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 空结果解释 */}
      {showNoDataExplainer && (
        <Card className="border-amber-500/40 bg-amber-500/10">
          <h3 className="text-sm font-bold uppercase tracking-wide text-amber-200 mb-3">
            ⚠️ 为什么没有查到结果？
          </h3>
          <div className="space-y-3 text-xs">
            <div className="flex items-start gap-2">
              <span className="text-amber-400">📌</span>
              <div>
                <span className="font-medium text-amber-100">原因</span>
                <p className="text-amber-200/80">
                  {noDataExplainer.reason_text ?? NO_DATA_REASONS[noDataExplainer.reason_code ?? '']?.label ?? '未知原因'}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2">
                <p className="text-amber-400">尝试平台</p>
                <p className="text-amber-100 font-medium">{noDataExplainer.attempted_platforms?.length ?? 0} 个</p>
              </div>
              <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2">
                <p className="text-amber-400">覆盖率</p>
                <p className="text-amber-100 font-medium">{Math.round((noDataExplainer.coverage_ratio ?? 0) * 100)}%</p>
              </div>
            </div>

            {noDataExplainer.suggested_queries && noDataExplainer.suggested_queries.length > 0 && (
              <div>
                <p className="font-medium text-amber-100 mb-2">💡 建议尝试的关键词</p>
                <div className="flex flex-wrap gap-2">
                  {noDataExplainer.suggested_queries.slice(0, 5).map((query, idx) => (
                    <span
                      key={idx}
                      className="rounded-full border border-amber-400/40 bg-amber-500/20 px-2 py-1 text-amber-200"
                    >
                      {query}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 人审触发提示 */}
      {humanReview?.required && (
        <Card className="border-red-500/40 bg-red-500/10">
          <div className="flex items-start gap-3">
            <span className="text-2xl">👤</span>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Badge variant="danger">需要人工复核</Badge>
                <span className="text-xs text-red-300">优先级：{humanReview.priority}</span>
              </div>
              <p className="mt-2 text-sm text-red-200">
                AI分析发现以下问题，建议人工介入核查：
              </p>
              <ul className="mt-2 space-y-1 text-xs text-red-100/80">
                {humanReview.reasons.map((reason, idx) => (
                  <li key={idx}>• {reason}</li>
                ))}
              </ul>
              {humanReview.handoff_packet && (
                <div className="mt-3 rounded border border-red-400/30 bg-red-950/30 p-2 text-xs">
                  <p className="text-red-200 font-medium">复核要点</p>
                  <p className="mt-1 text-red-100/70">{humanReview.handoff_packet.recommended_action}</p>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* 验证链路展示 */}
      <Card className="border-slate-700/80 bg-slate-900/70">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300 mb-4">
          验证链路（点击展开详情）
        </h3>

        <div className="space-y-2">
          {/* 多平台检索结果 */}
          <button
            onClick={() => setExpandedSection(expandedSection === 'sources' ? null : 'sources')}
            className="w-full rounded-lg border border-slate-700 bg-slate-950/50 p-3 text-left hover:border-slate-500 transition"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-200">
                📊 多平台检索：{run.search?.platform_count ?? 0} 个平台，{run.search?.total_posts ?? 0} 条结果
              </span>
              <span className="text-xs text-slate-500">{expandedSection === 'sources' ? '收起' : '展开'}</span>
            </div>
          </button>
          {expandedSection === 'sources' && run.search?.data && (
            <div className="rounded-lg border border-slate-700 bg-slate-950/30 p-3 text-xs space-y-2">
              {Object.entries(run.search.data).map(([platform, posts]) => (
                <div key={platform} className="flex items-center justify-between">
                  <span className="text-slate-300">{platform}</span>
                  <span className="text-slate-400">{Array.isArray(posts) ? posts.length : 0} 条</span>
                </div>
              ))}
            </div>
          )}

          {/* 支持性证据 */}
          {run.credibility?.evidence_chain && run.credibility.evidence_chain.length > 0 && (
            <button
              onClick={() => setExpandedSection(expandedSection === 'evidence' ? null : 'evidence')}
              className="w-full rounded-lg border border-emerald-500/40 bg-emerald-950/30 p-3 text-left hover:border-emerald-400 transition"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-emerald-200">
                  ✓ 支持性证据：{run.credibility.evidence_chain.length} 条
                </span>
                <span className="text-xs text-slate-500">{expandedSection === 'evidence' ? '收起' : '展开'}</span>
              </div>
            </button>
          )}
          {expandedSection === 'evidence' && run.credibility?.evidence_chain && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs space-y-2">
              {run.credibility.evidence_chain.slice(0, 5).map((item, idx) => (
                <div key={idx} className="text-emerald-200">
                  <span className="font-medium">[{item.step}]</span> {item.description}
                </div>
              ))}
            </div>
          )}

          {/* 异常检测 */}
          {run.credibility?.anomalies && run.credibility.anomalies.length > 0 && (
            <button
              onClick={() => setExpandedSection(expandedSection === 'anomalies' ? null : 'anomalies')}
              className="w-full rounded-lg border border-amber-500/40 bg-amber-950/30 p-3 text-left hover:border-amber-400 transition"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-amber-200">
                  ⚠️ 异常标记：{run.credibility.anomalies.length} 处
                </span>
                <span className="text-xs text-slate-500">{expandedSection === 'anomalies' ? '收起' : '展开'}</span>
              </div>
            </button>
          )}
          {expandedSection === 'anomalies' && run.credibility?.anomalies && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 text-xs space-y-2">
              {run.credibility.anomalies.map((item, idx) => (
                <div key={idx} className="text-amber-200">
                  <span className="font-medium">[{item.type}]</span> {item.platform}: {item.description}
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* 与其他产品对比 */}
      <Card className="border-slate-700/80 bg-slate-900/70">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300 mb-3">
          为什么选择 Aletheia
        </h3>
        <div className="grid gap-3 text-xs">
          <div className="flex items-start gap-2">
            <span className="text-emerald-400">✓</span>
            <div>
              <span className="font-medium text-slate-200">结论可核查</span>
              <p className="text-slate-500">每条结论都配套可执行的验证步骤，不是只给链接</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-emerald-400">✓</span>
            <div>
              <span className="font-medium text-slate-200">时效防滞后</span>
              <p className="text-slate-500">标注截至时间，证据过时自动降级并提示</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-emerald-400">✓</span>
            <div>
              <span className="font-medium text-slate-200">人机协同</span>
              <p className="text-slate-500">中高风险自动触发人工复核，不以效率牺牲准确性</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-amber-400">!</span>
            <div>
              <span className="font-medium text-slate-200">诚实面对不确定</span>
              <p className="text-slate-500">明确指出哪些点证据不足，不强行给出结论</p>
            </div>
          </div>
        </div>
      </Card>

      {/* 运行中提示 */}
      {isRunning && (
        <Card className="border-cyan-500/30 bg-cyan-500/10">
          <p className="text-sm text-cyan-200">🔄 分析仍在进行中，结论可能会更新...</p>
        </Card>
      )}
    </div>
  )
}