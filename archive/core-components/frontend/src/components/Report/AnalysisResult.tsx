import { useMemo, useState } from 'react'
import type { ExportFormat } from '../../api'
import type { FeedEvent, StreamedReasoningStep, VerificationRunState } from '../../types/runtime'
import { Badge, Button, Card, EmptyState } from '../common'
import { StepTimeline } from './StepTimeline'
import { DebateAnalysis } from './DebateAnalysis'
import { ConclusionCard } from './ConclusionCard'

interface AnalysisResultProps {
  run: VerificationRunState | null
  isRunning: boolean
  error: string | null
  isExporting: boolean
  onExport: (format: ExportFormat) => void
}

const STAGE_TITLE_MAP: Record<string, string> = {
  preprocessing: '预处理与主张抽取',
  physical_check: '物理一致性校验',
  logical_check: '逻辑链与谬误检测',
  source_analysis: '信源与账号画像分析',
  cross_validation: '多源交叉验证',
  anomaly_detection: '异常传播检测',
  evidence_synthesis: '证据综合',
  self_reflection: '自我反思与终判',
}

function stageTitle(stage: string) {
  return STAGE_TITLE_MAP[stage] || stage
}

function impactClass(value: number) {
  if (value > 0) return 'text-emerald-300'
  if (value < 0) return 'text-red-300'
  return 'text-slate-300'
}

function levelFromFeed(event: FeedEvent) {
  switch (event.level) {
    case 'success':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    case 'warning':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    case 'error':
      return 'bg-red-500/15 text-red-300 border-red-500/30'
    default:
      return 'bg-slate-700/60 text-slate-200 border-slate-600'
  }
}

function scoreColor(score: number) {
  if (score >= 0.7) return 'success'
  if (score >= 0.45) return 'warning'
  return 'danger'
}

function levelLabel(score: number) {
  if (score >= 0.7) return '较高可信'
  if (score >= 0.45) return '待复核'
  return '高风险'
}

function stepContext(step: StreamedReasoningStep, run: VerificationRunState): string[] {
  const contexts: string[] = []
  if (run.search) {
    contexts.push(
      `跨平台检索已返回 ${run.search.total_posts} 条结果，覆盖 ${run.search.platform_count} 个平台。`
    )
  }
  if (step.stage === 'anomaly_detection' && run.credibility?.anomalies?.length) {
    const anomalyText = run.credibility.anomalies
      .slice(0, 2)
      .map((item) => item.description)
      .join('；')
    contexts.push(`异常检测结果：${anomalyText}`)
  }
  if (step.stage === 'cross_validation' && run.credibility?.evidence_chain?.length) {
    contexts.push(`证据链参考：${run.credibility.evidence_chain[0]?.description ?? '无'}`)
  }
  if (step.stage === 'evidence_synthesis' && run.multiAgent?.consensus_points?.length) {
    contexts.push(`多Agent共识：${run.multiAgent.consensus_points.slice(0, 2).join('；')}`)
  }
  if (step.stage === 'self_reflection' && run.multiAgent?.recommendation) {
    contexts.push(`系统建议：${run.multiAgent.recommendation}`)
  }
  return contexts
}

export function AnalysisResult({
  run,
  isRunning,
  error,
  isExporting,
  onExport,
}: AnalysisResultProps) {
  const [activeStepIndex, setActiveStepIndex] = useState(0)

  const exportFormats: ExportFormat[] = ['md', 'pdf', 'docx', 'json']

  const activeStep = useMemo(() => {
    if (!run || run.streamSteps.length === 0) return null
    const index = Math.min(activeStepIndex, run.streamSteps.length - 1)
    return run.streamSteps[index]
  }, [activeStepIndex, run])

  if (!run) {
    return <EmptyState message="尚未启动核验任务，请先在“急救室核验入口”提交 claim。" />
  }

  const finalScore = run.analysis?.reasoning_chain.final_score ?? run.multiAgent?.overall_credibility ?? 0
  const finalRiskFlags = run.analysis?.reasoning_chain.risk_flags ?? run.multiAgent?.risk_flags ?? []
  const generatedArticle =
    typeof run.multiAgent?.generated_article === 'string'
      ? run.multiAgent?.generated_article
      : run.multiAgent?.generated_article?.body_markdown || ''
  const multiAgentLevel = run.multiAgent?.credibility_level
  const processingMs = run.analysis?.processing_time_ms ?? run.multiAgent?.processing_time_ms ?? 0

  return (
    <div className="space-y-5">
      <Card className="border-slate-700/80 bg-slate-900/70">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-black text-white">动态证据报告</h2>
            <p className="mt-1 text-sm text-slate-400">
              任务 ID: {run.runId} · 状态: {run.status} · 关键词: {run.keyword}
            </p>
            <p className="text-xs text-slate-500">
              启动于 {new Date(run.startedAt).toLocaleString('zh-CN')}
              {run.finishedAt ? ` · 完成于 ${new Date(run.finishedAt).toLocaleString('zh-CN')}` : ''}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={scoreColor(finalScore) as 'success' | 'warning' | 'danger'}>
              综合可信度 {Math.round(finalScore * 100)}% · {levelLabel(finalScore)}
            </Badge>
            {multiAgentLevel && (
              <Badge variant="info">
                Multi-Agent 结论 {multiAgentLevel}
              </Badge>
            )}
            <Badge variant="default">处理时长 {processingMs} ms</Badge>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
      </Card>

      <StepTimeline
        steps={run.streamSteps}
        activeStepIndex={Math.min(activeStepIndex, Math.max(run.streamSteps.length - 1, 0))}
        onStepClick={setActiveStepIndex}
      />

      {/* 新增：通俗化结论展示 */}
      <ConclusionCard run={run} isRunning={isRunning} />

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-4">
          {run.streamSteps.map((step, index) => (
            <Card
              key={`${step.stage}-${index}`}
              className={`border-slate-700/80 bg-slate-900/70 transition ${
                index === activeStepIndex ? 'ring-2 ring-cyan-300/60' : ''
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-500">Step {index + 1}</p>
                  <h3 className="text-lg font-bold text-slate-100">{stageTitle(step.stage)}</h3>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      step.status === 'done'
                        ? 'success'
                        : step.status === 'streaming'
                          ? 'info'
                          : 'default'
                    }
                  >
                    {step.status === 'done'
                      ? '已完成'
                      : step.status === 'streaming'
                        ? '流式输出中'
                        : '等待中'}
                  </Badge>
                  <Badge variant="default">置信度 {Math.round(step.confidence * 100)}%</Badge>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                <div className="rounded-xl border border-slate-700 bg-slate-950/80 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">推理文本</p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                    {step.streamedReasoning || '等待流式内容...'}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-700 bg-slate-950/80 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">阶段结论</p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-cyan-200">
                    {step.streamedConclusion || '等待结论输出...'}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Badge variant="default">
                    score_impact{' '}
                    <span className={`ml-1 font-semibold ${impactClass(step.score_impact)}`}>
                      {step.score_impact > 0 ? '+' : ''}
                      {step.score_impact.toFixed(2)}
                    </span>
                  </Badge>
                  <Badge variant="default">
                    时间 {new Date(step.timestamp).toLocaleTimeString('zh-CN')}
                  </Badge>
                </div>

                {step.evidence.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">证据项</p>
                    <div className="flex flex-wrap gap-2">
                      {step.evidence.map((item) => (
                        <span
                          key={`${step.stage}-${item}`}
                          className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200"
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {step.concerns.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">疑点项</p>
                    <div className="flex flex-wrap gap-2">
                      {step.concerns.map((item) => (
                        <span
                          key={`${step.stage}-${item}`}
                          className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-200"
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {stepContext(step, run).length > 0 && (
                  <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-3 text-sm text-indigo-100">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-300">
                      关联后端上下文
                    </p>
                    <ul className="space-y-1">
                      {stepContext(step, run).map((item) => (
                        <li key={`${step.stage}-ctx-${item}`}>• {item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>

        <div className="space-y-4">
          <Card className="border-slate-700/80 bg-slate-900/70">
            <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300">实时事件流</h3>
            <div className="mt-3 space-y-2">
              {run.feed.length === 0 && <p className="text-xs text-slate-500">等待事件...</p>}
              {run.feed.slice(0, 18).map((event) => (
                <div key={event.id} className={`rounded-lg border px-2.5 py-2 text-xs ${levelFromFeed(event)}`}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold">{event.source}</span>
                    <span>{new Date(event.time).toLocaleTimeString('zh-CN')}</span>
                  </div>
                  <p className="leading-5">{event.message}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card className="border-slate-700/80 bg-slate-900/70">
            <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300">生成文本（大模型）</h3>
            <p className="mt-2 text-xs text-slate-500">
              文本来源：multi-agent-analyze 的生成结果 + 后端推理链拼接。
            </p>
            <div className="mt-3 max-h-[360px] overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-sm leading-6 text-slate-200">
              {generatedArticle || run.generatedNarrative || '等待生成长文本...'}
            </div>
          </Card>

          <Card className="border-slate-700/80 bg-slate-900/70">
            <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300">报告导出</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {exportFormats.map((format) => (
                <Button
                  key={format}
                  size="sm"
                  variant="secondary"
                  disabled={isExporting || !run.generatedNarrative}
                  onClick={() => onExport(format)}
                >
                  {isExporting ? '导出中…' : `导出 ${format.toUpperCase()}`}
                </Button>
              ))}
            </div>
            {run.generatedReport && (
              <div className="mt-3 rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-xs text-slate-300">
                <p className="font-semibold text-slate-200">{run.generatedReport.title}</p>
                <p className="mt-1">报告ID: {run.generatedReport.id}</p>
                <p>可信度: {Math.round(run.generatedReport.credibility_score * 100)}%</p>
              </div>
            )}
          </Card>

          {finalRiskFlags.length > 0 && (
            <Card className="border-red-500/30 bg-red-500/10">
              <h3 className="text-sm font-bold uppercase tracking-wide text-red-200">风险标记</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {finalRiskFlags.map((flag) => (
                  <span
                    key={flag}
                    className="rounded-full border border-red-400/40 bg-red-500/20 px-2 py-1 text-xs text-red-100"
                  >
                    {flag}
                  </span>
                ))}
              </div>
            </Card>
          )}

          {activeStep && (
            <Card className="border-slate-700/80 bg-slate-900/70">

          {/* 辩论式推理展示 - 动画效果 */}
          <DebateAnalysis debate={run.multiAgent?.debate_analysis || null} />
              <p className="mt-2 text-sm text-slate-200">{stageTitle(activeStep.stage)}</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {activeStep.streamedConclusion || activeStep.streamedReasoning || '等待中...'}
              </p>
            </Card>
          )}
        </div>
      </div>

      {isRunning && (
        <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-200">
          后端任务仍在执行，报告内容将继续流式刷新。
        </div>
      )}
    </div>
  )
}
