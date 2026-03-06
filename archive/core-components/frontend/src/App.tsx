import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getInvestigationResult,
  getReportById,
  generateGeoReport,
  generatePublishSuggestions,
  listReports,
  previewInvestigation,
  runInvestigation,
  type InvestigationRunResult,
  type ReportResponse,
} from './api'
import { AdvancedForensicsPanel } from './components/program/AdvancedForensicsPanel'
import { MermaidCard } from './components/program/MermaidCard'
import { ProgramStageCard } from './components/program/ProgramStageCard'
import { ProgramTimeline } from './components/program/ProgramTimeline'
import { ReviewGateBanner } from './components/program/ReviewGateBanner'
import { extractEvidenceCards } from './lib/forensics'
import { JIMENG_URL, NANOBANANA_URL } from './lib/nanobanana'
import {
  deriveFreshness,
  deriveReviewGate,
  longConclusion,
  mapStepStatusToPhaseStatus,
  prettyReasonCode,
  shortConclusion,
} from './lib/programRuntime'
import { useProgramStore, mapStepIdToPhase } from './store/programStore'
import type { LogItem, ProgramPhase } from './types/runtime'

const defaultPlatforms = ['weibo', 'xinhua', 'news', 'xiaohongshu', 'zhihu']
type ConsoleSection =
  | 'dashboard'
  | 'tasks'
  | 'analysis'
  | 'conclusions'
  | 'archives'
  | 'settings'

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

function DynamicMark() {
  return <span className="dynamic-mark">动态</span>
}

function truncateText(value: string, maxLen = 90) {
  if (value.length <= maxLen) return value
  return `${value.slice(0, maxLen)}…`
}

function getEvidenceMeta(payload?: Record<string, unknown>) {
  if (!payload || typeof payload !== 'object') return null
  const card = (payload as Record<string, unknown>).evidence_card
  if (!card || typeof card !== 'object') return null
  const cardObj = card as Record<string, unknown>
  const url = typeof cardObj.url === 'string' ? cardObj.url : ''
  const snippet = typeof cardObj.snippet === 'string' ? cardObj.snippet : ''
  const title = typeof cardObj.title === 'string' ? cardObj.title : ''
  const source = typeof cardObj.source_name === 'string' ? cardObj.source_name : ''
  return { url, snippet, title, source }
}

const EVIDENCE_LOG_MIN_RELEVANCE = 0.22

function getEvidenceScore(payload?: Record<string, unknown>): number {
  if (!payload || typeof payload !== 'object') return 0
  const card = (payload as Record<string, unknown>).evidence_card
  if (!card || typeof card !== 'object') return 0
  const score = Number((card as Record<string, unknown>).relevance_score || 0)
  return Number.isFinite(score) ? score : 0
}

function isRelevantEvidenceLog(log: LogItem): boolean {
  if (String(log.type || '') !== 'evidence_found') return false
  const payload = log.payload
  if (!payload || typeof payload !== 'object') return false
  const card = (payload as Record<string, unknown>).evidence_card
  if (!card || typeof card !== 'object') return false
  const cardObj = card as Record<string, unknown>
  const score = getEvidenceScore(payload)
  const keywordMatch = Boolean(cardObj.keyword_match)
  const entityPass = cardObj.entity_pass === undefined ? true : Boolean(cardObj.entity_pass)
  const dropReason = String(cardObj.drop_reason || '').trim()
  const status = String(cardObj.validation_status || '').toLowerCase()
  const lowQualityStatus = new Set(['provisional_low_relevance', 'url_only', 'invalid', 'unreachable'])
  if (dropReason) return false
  if (lowQualityStatus.has(status)) return false
  return score >= EVIDENCE_LOG_MIN_RELEVANCE && keywordMatch && entityPass
}

function buildEvidenceDisplayLogs(rawLogs: LogItem[]): LogItem[] {
  const evidenceLogs = (rawLogs || [])
    .filter((log) => isRelevantEvidenceLog(log))
    .sort((a, b) => getEvidenceScore(b.payload) - getEvidenceScore(a.payload))
  const nonEvidenceLogs = (rawLogs || [])
    .filter((log) => String(log.type || '') !== 'evidence_found')
    .slice(0, 40)
    .reverse()
  const merged = [...evidenceLogs, ...nonEvidenceLogs]
  return merged.slice(0, 120)
}

function MyWorkspace({
  result,
  reports,
  reviewTasks,
  replayResult,
  onCloseReviewTask,
  onOpenReport,
}: {
  result: InvestigationRunResult | null
  reports: ReportResponse[]
  reviewTasks: Array<{
    id: string
    runId: string
    createdAt: string
    priority: 'low' | 'medium' | 'high'
    reasons: string[]
    status: 'open' | 'closed'
  }>
  replayResult: InvestigationRunResult | null
  onCloseReviewTask: (taskId: string) => void
  onOpenReport: (id: string) => void
}) {
  const claimAnalysis = (result?.claim_analysis || {}) as Record<string, unknown>
  const reviewQueue = Array.isArray(claimAnalysis?.review_queue)
    ? (claimAnalysis.review_queue as Array<Record<string, unknown>>)
    : []
  const claimReasoning = Array.isArray(claimAnalysis?.claim_reasoning)
    ? (claimAnalysis.claim_reasoning as Array<Record<string, unknown>>)
    : []

  const todoItems = [
    `运行结论：${String(claimAnalysis?.run_verdict || 'UNCERTAIN')}`,
    `待人工复核：${reviewQueue.length} 条`,
    `主张分析条数：${Array.isArray(claimAnalysis?.claims) ? claimAnalysis.claims.length : 0}`,
  ]
  const replaySteps = Array.isArray(replayResult?.step_summaries) && replayResult?.step_summaries?.length
    ? (replayResult.step_summaries as Array<Record<string, unknown>>)
    : Array.isArray(replayResult?.steps)
      ? (replayResult.steps as Array<Record<string, unknown>>)
      : []

  return (
    <section className="my-layout">
      <article className="panel-card">
        <div className="panel-head">
          <h2>我的待办</h2>
          <span>My Queue</span>
        </div>
        <ul className="list-plain">
          {todoItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        {reviewQueue.slice(0, 6).map((item, idx) => (
          <p key={idx} className="hint-line">
            - {String(item.claim_id || 'unknown')}: {(item.reasons as string[] | undefined)?.join(' / ') || '待复核'}
          </p>
        ))}
        {reviewTasks.slice(0, 6).map((task) => (
          <div key={task.id} className="review-task">
            <p>#{task.runId.slice(0, 8)} · {task.priority.toUpperCase()} · {new Date(task.createdAt).toLocaleString('zh-CN')}</p>
            <small>{task.reasons.join('；')}</small>
            {task.status === 'open' && (
              <button type="button" className="ghost-btn mini" onClick={() => onCloseReviewTask(task.id)}>标记已处理</button>
            )}
          </div>
        ))}
      </article>

      <article className="panel-card">
        <div className="panel-head">
          <h2>历史回放</h2>
          <span>Replay</span>
        </div>
        {replayResult ? (
          <div className="replay-list">
            <p className="hint-line">Run: {replayResult.run_id} · 状态: {replayResult.status}</p>
            {replaySteps.length === 0 && <p className="empty-copy">该报告缺少可回放步骤数据。</p>}
            {replaySteps.slice(0, 12).map((step, idx) => (
              <div key={idx} className="replay-item">
                <p>{String(step.step_id || step.id || `step_${idx + 1}`)}</p>
                <small>{String(step.status || step.state || 'unknown')} · {String(step.summary || step.detail || '无摘要')}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-copy">点击“历史报告”中的条目后，可在此回放阶段过程。</p>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-head">
          <h2>历史报告</h2>
          <span>History</span>
        </div>
        <div className="history-list">
          {reports.length === 0 && <p className="empty-copy">暂无历史报告</p>}
          {reports.map((report) => (
            <button
              key={report.id}
              type="button"
              className="history-item"
              onClick={() => onOpenReport(report.id)}
            >
              <span>{report.title}</span>
              <span>{Math.round(report.credibility_score * 100)}%</span>
            </button>
          ))}
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-head">
          <h2>修改建议</h2>
          <span>Suggestions</span>
        </div>
        {claimReasoning.length === 0 && <p className="empty-copy">暂无建议，等待核验结果。</p>}
        {claimReasoning.slice(0, 5).map((row, idx) => (
          <div key={idx} className="suggestion-item">
            <p className="suggestion-title">{String(row.claim_id || 'Claim')}</p>
            <p className="suggestion-text">{String(row.conclusion_text || '建议补充证据与上下文')}</p>
          </div>
        ))}
      </article>
    </section>
  )
}

function App() {
  const [claim, setClaim] = useState('')
  const [keyword, setKeyword] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [platformCsv] = useState(defaultPlatforms.join(','))
  const [useAutoPlatforms] = useState(true)
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [replayResult, setReplayResult] = useState<InvestigationRunResult | null>(null)
  const [activeSection, setActiveSection] = useState<ConsoleSection>('dashboard')
  const [humanConfirmChecked, setHumanConfirmChecked] = useState(false)
  const [isPublishing, setIsPublishing] = useState(false)
  const [isGeoGenerating, setIsGeoGenerating] = useState(false)
  const [publishError, setPublishError] = useState('')
  const [geoReport, setGeoReport] = useState<ReportResponse | null>(null)
  const [openStages, setOpenStages] = useState<Record<ProgramPhase, boolean>>({
    preview: false,
    evidence: false,
    verification: false,
    conclusion: false,
  })

  const {
    runId,
    runStatus,
    preview,
    result,
    streamEvents,
    phaseLogs,
    awaitingHumanConfirm,
    humanNotes,
    humanConfirmedAt,
    publishSuggestions,
    phaseNodes,
    currentPhase,
    freshness,
    reviewGate,
    reviewTasks,
    reportHistory,
    setPreview,
    setRunMeta,
    setResult,
    pushStreamEvent,
    pushPhaseLog,
    setAwaitingHumanConfirm,
    setHumanNotes,
    setHumanConfirmedAt,
    setPublishSuggestions,
    setPhaseStatus,
    setCurrentPhase,
    setFreshness,
    setReviewGate,
    addReviewTask,
    closeReviewTask,
    setReportHistory,
    resetRun,
  } = useProgramStore()

  const phaseRefs = useRef<Record<ProgramPhase, HTMLDivElement | null>>({
    preview: null,
    evidence: null,
    verification: null,
    conclusion: null,
  })
  const evidenceLogRef = useRef<HTMLUListElement | null>(null)

  useEffect(() => {
    const ref = phaseRefs.current[currentPhase]
    if (ref) {
      ref.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [currentPhase])

  useEffect(() => {
    const ctrl = new AbortController()
    void listReports(1, 20, ctrl.signal)
      .then((resp) => setReportHistory(resp.items))
      .catch(() => undefined)
    return () => ctrl.abort()
  }, [setReportHistory])

  useEffect(() => {
    const logList = evidenceLogRef.current
    if (logList) {
      logList.scrollTop = logList.scrollHeight
    }
  }, [phaseLogs.evidence, openStages.evidence])

  const summaryBars = useMemo(() => {
    const acq = (result?.acquisition_report || {}) as Record<string, unknown>
    const valid = Number(acq.external_evidence_count || 0)
    const primary = Number(acq.external_primary_count || 0)
    const background = Number(acq.external_background_count || 0)
    const total = Math.max(1, valid)
    return [
      { label: '主证据', value: primary, pct: Math.round((primary / total) * 100) },
      { label: '背景证据', value: background, pct: Math.round((background / total) * 100) },
      { label: '总有效证据', value: valid, pct: 100 },
    ]
  }, [result])

  const runOverview = useMemo(() => {
    const duration = typeof result?.duration_sec === 'number' ? `${result.duration_sec.toFixed(1)}s` : '--'
    return {
      duration,
      runStatus: result?.status || runStatus || 'idle',
      eventCount: streamEvents.length,
    }
  }, [result, runStatus, streamEvents.length])

  const freshnessText = useMemo(() => {
    if (freshness.status === 'FRESH' || freshness.status === 'RECENT') return `信息时效正常（最近证据：${freshness.latest_evidence_at || '未知'}）`
    if (freshness.status === 'STALE') return `信息可能滞后（最近证据：${freshness.latest_evidence_at || '未知'}）`
    return '信息时效未知，建议补检最新来源'
  }, [freshness])

  const verificationChecklist = useMemo(() => extractEvidenceCards(result).slice(0, 3), [result])
  const showTimeline = useMemo(
    () => Boolean(humanConfirmedAt || streamEvents.length > 0),
    [humanConfirmedAt, streamEvents.length]
  )
  const previewPlatforms = useMemo(() => {
    const plan = (preview?.source_plan || {}) as Record<string, unknown>
    const platforms = plan.selected_platforms
    const fromPlan = Array.isArray(platforms) ? platforms.map((item) => String(item)) : []
    if (fromPlan.length) return fromPlan
    if (useAutoPlatforms) return []
    const manual = platformCsv
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    return manual
  }, [preview, platformCsv, useAutoPlatforms])
  const previewClaims = useMemo(() => preview?.claims_draft ?? [], [preview])
  const phaseTitleMap = useMemo(() => {
    const map = new Map<ProgramPhase, string>()
    phaseNodes.forEach((phase) => map.set(phase.key, phase.title))
    return map
  }, [phaseNodes])
  const thinkingFeed = useMemo(() => {
    const entries = Object.entries(phaseLogs) as [ProgramPhase, LogItem[]][]
    const flattened = entries.flatMap(([phase, items]) => items.map((item) => ({ phase, ...item })))
    return flattened
      .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime())
      .slice(-6)
  }, [phaseLogs])

  async function openHistoryReport(reportId: string) {
    setError('')
    try {
      const report = await getReportById(reportId)
      const tag = (report.tags || []).find((x) => String(x).startsWith('run_'))
      if (!tag) return
      const restoredRunId = String(tag).replace(/^run_/, '')
      const restored = await getInvestigationResult(restoredRunId)
      setReplayResult(restored)
      setRunMeta({ runId: restoredRunId, runStatus: restored.status || 'completed' })
      setResult(restored)
      setFreshness(deriveFreshness(restored))
      setReviewGate(deriveReviewGate(restored))
      setActiveSection('archives')
      setPhaseStatus('conclusion', {
        status: 'done',
        summary: '已从历史报告回放结果',
        actionHint: '可查看高级核查详情复盘证据链',
      })
      setCurrentPhase('conclusion')
    } catch (e) {
      setError(e instanceof Error ? e.message : '历史报告回放失败')
    }
  }

  function buildLog(message: string, type = 'info', payload?: Record<string, unknown>) {
    return {
      ts: new Date().toISOString(),
      type,
      message,
      payload,
    }
  }

  function isTerminalStatus(status?: string) {
    return ['completed', 'failed', 'error'].includes(String(status || '').toLowerCase())
  }

  function updatePhaseByStep(stepId: string, status: string) {
    const phase = mapStepIdToPhase(stepId)
    setCurrentPhase(phase)
    setPhaseStatus(phase, { status: mapStepStatusToPhaseStatus(status) })
  }

  async function handleRun() {
    if (!claim.trim() || isBusy) return
    setIsBusy(true)
    setError('')
    resetRun()
    setOpenStages({ preview: false, evidence: false, verification: false, conclusion: false })
    setHumanConfirmChecked(false)
    setPublishError('')
    setGeoReport(null)
    setPublishSuggestions(null)

    const manualPlatforms = platformCsv
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    const platforms = useAutoPlatforms ? undefined : (manualPlatforms.length ? manualPlatforms : undefined)

    const effectiveKeyword = keyword.trim() || claim.trim().slice(0, 30)

    try {
      setPhaseStatus('preview', { status: 'running', summary: '正在生成预分析', actionHint: '确认主张草案与平台选择' })
      const previewResp = await previewInvestigation({
        claim: claim.trim(),
        keyword: effectiveKeyword,
        source_url: sourceUrl.trim() || undefined,
        platforms,
        mode: 'dual',
        source_strategy: 'auto',
      })
      setPreview(previewResp)
      setPhaseStatus('preview', {
        status: previewResp.status === 'ready' ? 'done' : 'partial',
        summary: previewResp.intent_summary || '预分析已返回',
        actionHint: '请人工确认并补充说明后启动采集',
      })
      setAwaitingHumanConfirm(true)
      pushPhaseLog('preview', buildLog('预分析完成，等待人工确认', 'preview_ready', { preview_id: previewResp.preview_id }))
      setCurrentPhase('preview')
    } catch (e) {
      setError(e instanceof Error ? e.message : '运行失败')
      setPhaseStatus('conclusion', {
        status: 'error',
        summary: '任务执行失败，请查看错误提示并重试。',
        actionHint: '检查网络与后端状态后重试',
      })
      setCurrentPhase('conclusion')
    } finally {
      setIsBusy(false)
    }
  }

  async function confirmAndRun() {
    if (!preview || isBusy) return
    if (!humanConfirmChecked) {
      setError('请先确认预分析结果后再启动采集')
      return
    }
    setIsBusy(true)
    setError('')
    setAwaitingHumanConfirm(false)
    const confirmedAt = new Date().toISOString()
    setHumanConfirmedAt(confirmedAt)
    pushPhaseLog(
      'preview',
      buildLog(`人工确认完成${humanNotes ? `：${humanNotes}` : ''}`, 'human_confirmed', {
        confirmed_at: confirmedAt,
      })
    )

    const manualPlatforms = platformCsv
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    const confirmedPlatforms = useAutoPlatforms ? previewPlatforms : manualPlatforms
    const platforms = confirmedPlatforms.length ? confirmedPlatforms : undefined
    const effectiveKeyword = keyword.trim() || claim.trim().slice(0, 30)

    try {
      setPhaseStatus('preview', {
        summary: '人工已确认，进入采集阶段',
        actionHint: '系统将开始多平台采集',
      })

      setCurrentPhase('evidence')
      setPhaseStatus('evidence', { status: 'running', summary: '正在采集多源证据', actionHint: '观察覆盖率与空结果解释' })

      const accepted = await runInvestigation({
        claim: claim.trim(),
        keyword: effectiveKeyword,
        source_url: sourceUrl.trim() || undefined,
        platforms,
        mode: 'dual',
        audience_profile: 'both',
        human_notes: humanNotes.trim() || undefined,
        confirmed_preview_id: preview.preview_id,
        confirmed_claims: preview.claims_draft.map((x) => x.text),
        confirmed_platforms: platforms,
      })
      setRunMeta({ runId: accepted.run_id, runStatus: accepted.initial_status })

      await new Promise<void>((resolve) => {
        const source = new EventSource(`${(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1')}/investigations/${accepted.run_id}/stream`)
        const timeout = setTimeout(() => {
          source.close()
          resolve()
        }, 120000)

        source.onmessage = () => {
          // keep alive
        }

        source.addEventListener('heartbeat', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'heartbeat', payload })
            const status = String(payload.status || 'running')
            pushPhaseLog(currentPhase, buildLog(`运行心跳：${status}`, 'heartbeat', payload))
          } catch {
            // ignore
          }
        })

        source.addEventListener('step_update', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'step_update', payload })
            const stepId = String(payload.step_id || '')
            updatePhaseByStep(stepId, String(payload.status || 'running'))
            const phase = mapStepIdToPhase(stepId)
            pushPhaseLog(phase, buildLog(`步骤更新：${stepId} (${String(payload.status || 'running')})`, 'step_update', payload))
            if (stepId === 'multi_agent') {
              setPhaseStatus('verification', {
                summary: `核验进展：${String(payload.status || 'running')} · 覆盖平台 ${String(payload.platforms_with_data || '--')}`,
              })
            }
          } catch {
            // ignore malformed events
          }
        })

        source.addEventListener('warning', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'warning', payload })
            const stepId = String(payload.step_id || '')
            const phase = stepId ? mapStepIdToPhase(stepId) : currentPhase
            pushPhaseLog(phase, buildLog(`警告：${String(payload.message || payload.code || '未知')}`, 'warning', payload))
          } catch {
            // ignore
          }
        })

        source.addEventListener('evidence_found', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'evidence_found', payload })
            pushPhaseLog('evidence', buildLog('发现新证据', 'evidence_found', payload))
          } catch {
            // ignore
          }
        })

        source.addEventListener('source_plan_ready', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'source_plan_ready', payload })
            pushPhaseLog('preview', buildLog('来源规划已就绪', 'source_plan_ready', payload))
          } catch {
            // ignore
          }
        })

        source.addEventListener('agent_vote', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'agent_vote', payload })
            pushPhaseLog('verification', buildLog('多 Agent 投票完成', 'agent_vote', payload))
          } catch {
            // ignore
          }
        })

        source.addEventListener('platform_analysis_ready', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data || '{}') as Record<string, unknown>
            pushStreamEvent({ type: 'platform_analysis_ready', payload })
            const platform = String(payload.platform || 'unknown')
            const score = Number(payload.score || 0)
            const summary = String(payload.summary || '')
            pushPhaseLog(
              'verification',
              buildLog(
                `平台实时分析完成：${platform} · score=${score.toFixed(2)}${summary ? ` · ${summary}` : ''}`,
                'platform_analysis_ready',
                payload,
              ),
            )
          } catch {
            // ignore
          }
        })

        source.addEventListener('run_completed', () => {
          clearTimeout(timeout)
          source.close()
          pushPhaseLog('conclusion', buildLog('运行完成', 'run_completed'))
          resolve()
        })

        source.addEventListener('run_failed', () => {
          clearTimeout(timeout)
          source.close()
          pushPhaseLog('conclusion', buildLog('运行失败', 'run_failed'))
          resolve()
        })

        source.onerror = () => {
          clearTimeout(timeout)
          source.close()
          resolve()
        }
      })

      const final = await getInvestigationResult(accepted.run_id)
      setResult(final)
      setFreshness(deriveFreshness(final))
      const terminal = isTerminalStatus(final.status)

      if (terminal) {
        const gate = deriveReviewGate(final)
        setReviewGate(gate)
        if (gate.required) {
          addReviewTask({
            runId: accepted.run_id,
            priority: gate.priority,
            reasons: gate.reasons,
          })
        }

        const nd = final.no_data_explainer
        if (nd) {
          setPhaseStatus('evidence', {
            status: 'partial',
            summary: `采集有缺口：${prettyReasonCode(nd.reason_code)}`,
            actionHint: '按建议补检词二次核查',
          })
        } else {
          setPhaseStatus('evidence', { status: 'done', summary: '证据采集完成', actionHint: '进入核验冲突分析' })
        }

        setPhaseStatus('verification', {
          status: 'done',
          summary: `主张结论：${String(((final.claim_analysis || {}) as Record<string, unknown>).run_verdict || 'UNCERTAIN')}`,
          actionHint: '检查冲突点并决定是否人审',
        })

        setPhaseStatus('conclusion', {
          status: 'done',
          summary: shortConclusion(final),
          actionHint: '优先查看双层结论、时效状态与复核建议',
        })
        setCurrentPhase('conclusion')

        const reports = await listReports(1, 20)
        setReportHistory(reports.items)
      } else {
        setPhaseStatus('conclusion', {
          status: 'pending',
          summary: '运行中，等待结论生成',
          actionHint: '等待采集与核验完成',
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '运行失败')
      setPhaseStatus('conclusion', {
        status: 'error',
        summary: '任务执行失败，请查看错误提示并重试。',
        actionHint: '检查网络与后端状态后重试',
      })
      setCurrentPhase('conclusion')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleGenerateSuggestions() {
    if (!runId || !result) {
      setPublishError('请先完成一次核验再生成发布建议。')
      return
    }
    setIsPublishing(true)
    setPublishError('')
    try {
      const resp = await generatePublishSuggestions(runId)
      setPublishSuggestions(resp)
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : '发布建议生成失败')
    } finally {
      setIsPublishing(false)
    }
  }

  async function handleGenerateGeoReport() {
    if (!runId || !result) {
      setPublishError('请先完成一次核验再生成 GEO 报告。')
      return
    }
    setIsGeoGenerating(true)
    setPublishError('')
    try {
      const report = await generateGeoReport(runId)
      setGeoReport(report)
      const reports = await listReports(1, 20)
      setReportHistory(reports.items)
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : 'GEO 报告生成失败')
    } finally {
      setIsGeoGenerating(false)
    }
  }

  function renderPublishPanel(variant: 'inline' | 'full') {
    return (
      <section className={cn('panel-card', 'publish-panel', variant === 'inline' && 'publish-inline')}>
        <div className="panel-head">
          <h3>发布与复核建议</h3>
          <span>结论后行动</span>
        </div>
        <p className="stage-summary">用于二次编辑、对外发布与人工复核交接。</p>
        <ul className="list-plain">
          <li>短结论：{shortConclusion(result)}</li>
          <li>时效状态：{freshness.status}</li>
          <li>人工复核：{reviewGate.required ? `需要（${reviewGate.priority.toUpperCase()}）` : '当前不需要'}</li>
        </ul>
        <div className="publish-actions">
          <button type="button" className="primary-btn" disabled={isPublishing || !runId || !result} onClick={handleGenerateSuggestions}>
            {isPublishing ? '生成中...' : '生成推文建议'}
          </button>
          <button type="button" className="ghost-btn" disabled={isGeoGenerating || !runId || !result} onClick={handleGenerateGeoReport}>
            {isGeoGenerating ? '生成中...' : '一键生成 GEO 报告'}
          </button>
          {publishError && <span className="error-text">{publishError}</span>}
        </div>

        <div className="verify-list">
          <p className="verify-title">可核查要点（发布前建议附上）</p>
          {verificationChecklist.length === 0 && <p className="empty-copy">暂无可核查条目。</p>}
          {verificationChecklist.map((item) => (
            <a key={item.id} href={item.url} target="_blank" rel="noreferrer noopener" className="verify-item">
              <span>{item.platform} · {item.publishedAt || '时间未知'}</span>
              <strong>{item.title}</strong>
            </a>
          ))}
        </div>

        <div className="publish-grid">
          <article className="sub-card">
            <div className="sub-head">
              <h4>推文建议</h4>
              <span className="sub-meta">3 条中文</span>
            </div>
            {publishSuggestions?.tweet_suggestions?.length ? (
              <div className="tweet-list">
                {publishSuggestions.tweet_suggestions.map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="tweet-item">
                    <p className="tweet-title">{item.title}</p>
                    <p className="tweet-text">{item.text}</p>
                    <div className="tweet-meta">
                      <span>{item.angle || '传播角度'}</span>
                      <span>{(item.hashtags || []).join(' ')}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-copy">点击“生成推文建议”后展示。</p>
            )}
          </article>

          <MermaidCard
            title="方向思维导图"
            subtitle="Mermaid mindmap"
            definition={publishSuggestions?.mindmap_mermaid || ''}
          />

          <article className="sub-card">
            <div className="sub-head">
              <h4>创新写作方向</h4>
              <span className="sub-meta">方向清单</span>
            </div>
            {publishSuggestions?.creative_directions?.length ? (
              <ul className="list-plain compact">
                {publishSuggestions.creative_directions.map((item, idx) => (
                  <li key={`${item}-${idx}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="empty-copy">等待生成。</p>
            )}
          </article>

          <article className="sub-card">
            <div className="sub-head">
              <h4>热点利好提炼</h4>
              <span className="sub-meta">价值点</span>
            </div>
            {publishSuggestions?.hotspot_benefits?.length ? (
              <ul className="list-plain compact">
                {publishSuggestions.hotspot_benefits.map((item, idx) => (
                  <li key={`${item}-${idx}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="empty-copy">等待生成。</p>
            )}
          </article>
        </div>

        <article className="sub-card geo-report">
          <div className="sub-head">
            <h4>GEO 新闻报告</h4>
            <span className="sub-meta">自动落库</span>
          </div>
          {geoReport ? (
            <div className="geo-summary">
              <p className="geo-title">{geoReport.title}</p>
              <p className="geo-text">{geoReport.summary}</p>
            </div>
          ) : (
            <p className="empty-copy">点击按钮生成 GEO 报告并保存到历史报告。</p>
          )}
        </article>

        <article className="sub-card">
          <div className="sub-head">
            <h4>图像化总结（预留）</h4>
            <span className="sub-meta">仅链接占位</span>
          </div>
          <p className="hint-text">后续由 Agent 自动拆解信息并生成 Nano Banana/即梦提示词，产出总结可视化图。</p>
          <div className="nano-links">
            {NANOBANANA_URL && <a href={NANOBANANA_URL} target="_blank" rel="noreferrer noopener">Nano Banana 使用</a>}
            {JIMENG_URL && <a href={JIMENG_URL} target="_blank" rel="noreferrer noopener">即梦 使用</a>}
          </div>
        </article>
      </section>
    )
  }

  const runningCount = runStatus && !isTerminalStatus(runStatus) ? 1 : 0
  const openReviewCount = reviewTasks.filter((task) => task.status === 'open').length
  const todayCompleted = reportHistory.length

  return (
    <div className="console-root">
      <aside className="console-sidebar">
        <div className="brand-block">
          <div className="brand-mark" />
          <div>
            <h1>Aletheia</h1>
            <p>Newsroom Truth Console</p>
          </div>
        </div>

        <nav className="console-nav">
          <button type="button" className={cn('nav-item', activeSection === 'dashboard' && 'is-active')} onClick={() => setActiveSection('dashboard')}>
            控制台
          </button>
          <button type="button" className={cn('nav-item', activeSection === 'tasks' && 'is-active')} onClick={() => setActiveSection('tasks')}>
            任务管理
          </button>
          <button type="button" className={cn('nav-item', activeSection === 'analysis' && 'is-active')} onClick={() => setActiveSection('analysis')}>
            分析中心
          </button>
          <button type="button" className={cn('nav-item', activeSection === 'conclusions' && 'is-active')} onClick={() => setActiveSection('conclusions')}>
            结论管理
          </button>
          <button type="button" className={cn('nav-item', activeSection === 'archives' && 'is-active')} onClick={() => setActiveSection('archives')}>
            历史档案
          </button>
          <button type="button" className={cn('nav-item', activeSection === 'settings' && 'is-active')} onClick={() => setActiveSection('settings')}>
            系统设置
          </button>
        </nav>
      </aside>

      <div className="console-body">
        <header className="console-topbar">
          <div className="topbar-left">
            <span className="brand-title">Aletheia Newsroom Truth Console</span>
            <span className="brand-tag">B2B Fact Check</span>
          </div>
          <div className="topbar-center">
            <div className="status-chip">运行中：{runningCount}</div>
            <div className="status-chip warning">待复核：{openReviewCount}</div>
            <div className="status-chip success">今日完成：{todayCompleted}</div>
          </div>
          <div className="topbar-right">
            <input className="global-search" placeholder="搜索任务ID / 主张 / 报告" />
            <button type="button" className="ghost-btn">通知</button>
            <button type="button" className="ghost-btn">帮助</button>
            <div className="user-pill">Admin</div>
          </div>
        </header>

        <main className="console-content">
          {activeSection === 'dashboard' && (
            <section className="dashboard-grid">
              <div className="dashboard-main">
                <section className="panel-card input-card">
                  <div className="panel-head">
                    <h3>主张核验控制台</h3>
                    <span>预分析 → 采集 → 核验 → 结论</span>
                  </div>
                  <textarea
                    data-testid="claim-input"
                    value={claim}
                    onChange={(e) => setClaim(e.target.value)}
                    placeholder="输入需要核验的新闻/主张/言论内容"
                    rows={5}
                  />
                  <div className="input-row">
                    <input data-testid="keyword-input" value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="关键词" />
                    <input data-testid="url-input" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="网页 URL" />
                  </div>
                  <div className="platform-row auto-source-row">
                    <div className="auto-source-indicator">
                      <span className="auto-source-dot" />
                      AI 自动选源
                    </div>
                    <span className="hint-text">系统将自动规划权威媒体与社交信源</span>
                  </div>
                  <div className="form-actions">
                    <button data-testid="start-run" type="button" className="primary-btn" disabled={isBusy || !claim.trim()} onClick={handleRun}>
                      {isBusy ? '启动中...' : '启动核验'}
                    </button>
                    <span className="hint-text">复杂核验详情在分析中心查看。</span>
                  </div>
                  {error && <p className="error-text">{error}</p>}
                </section>

                {preview && awaitingHumanConfirm && (
                  <section className="panel-card human-confirm">
                    <div className="panel-head">
                      <h3>预分析确认</h3>
                      <span>人工介入</span>
                    </div>
                    <p className="stage-summary">意图摘要：{preview.intent_summary}</p>
                    <div className="chip-row">
                      <span className="chip">预分析状态：{preview.status}</span>
                      <span className="chip">事件类型：{preview.event_type}</span>
                      <span className="chip">领域：{preview.domain}</span>
                    </div>
                    <div className="confirm-grid">
                      <div>
                        <p className="hint-text">来源计划（AI 选型）：</p>
                        <div className="chip-row">
                          {(previewPlatforms.length ? previewPlatforms : ['待选择']).map((item) => (
                            <span key={item} className="chip">{item}</span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="hint-text">主张草案：</p>
                        <ul className="list-plain compact">
                          {previewClaims.length === 0 && <li>暂无主张草案</li>}
                          {previewClaims.map((draft) => (
                            <li key={draft.claim_id}>{draft.text}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <textarea
                      value={humanNotes}
                      onChange={(e) => setHumanNotes(e.target.value)}
                      placeholder="人工补充或修订说明（可选）"
                      rows={3}
                    />
                    <div className="confirm-actions">
                      <label className="confirm-check">
                        <input
                          type="checkbox"
                          checked={humanConfirmChecked}
                          onChange={(e) => setHumanConfirmChecked(e.target.checked)}
                          disabled={!awaitingHumanConfirm}
                        />
                        <span>我已确认 AI 选型与主张草案</span>
                      </label>
                      <button
                        type="button"
                        className="primary-btn"
                        disabled={!awaitingHumanConfirm || !humanConfirmChecked || isBusy}
                        onClick={confirmAndRun}
                      >
                        {isBusy ? '启动中...' : '确认并继续'}
                      </button>
                      {humanConfirmedAt && (
                        <span className="hint-text">已确认：{new Date(humanConfirmedAt).toLocaleString('zh-CN')}</span>
                      )}
                    </div>
                  </section>
                )}

                <section className="panel-card running-tasks">
                  <div className="panel-head">
                    <h3>运行中任务</h3>
                    <span>最近 3 条</span>
                  </div>
                  {!runId && <p className="empty-copy">暂无运行中的任务</p>}
                  {runId && (
                    <div className="task-row">
                      <div>
                        <p>任务ID：{runId}</p>
                        <small>状态：{runOverview.runStatus} · 耗时：{runOverview.duration}</small>
                      </div>
                      <button type="button" className="ghost-btn" onClick={() => setActiveSection('tasks')}>查看详情</button>
                    </div>
                  )}
                </section>
              </div>

              <aside className="dashboard-side">
                <article className="panel-card">
                  <div className="panel-head">
                    <h3>今日数据看板</h3>
                    <span>概览</span>
                  </div>
                  <div className="metric-row">
                    <span>今日发起</span>
                    <strong>{todayCompleted}</strong>
                  </div>
                  <div className="metric-row">
                    <span>待复核</span>
                    <strong>{openReviewCount}</strong>
                  </div>
                  <div className="metric-row">
                    <span>证据采集总量</span>
                    <strong>{summaryBars[2]?.value ?? 0}</strong>
                  </div>
                </article>

                <article className="panel-card">
                  <div className="panel-head">
                    <h3>待办提醒</h3>
                    <span>人工复核</span>
                  </div>
                  {reviewTasks.slice(0, 5).map((task) => (
                    <div key={task.id} className="review-task">
                      <p>#{task.runId.slice(0, 8)} · {task.priority.toUpperCase()}</p>
                      <small>{task.reasons.join('；')}</small>
                    </div>
                  ))}
                  {reviewTasks.length === 0 && <p className="empty-copy">暂无待办</p>}
                </article>

                <article className="panel-card">
                  <div className="panel-head">
                    <h3>最近完成任务</h3>
                    <span>结论标签</span>
                  </div>
                  {reportHistory.slice(0, 5).map((report) => (
                    <button key={report.id} type="button" className="history-item" onClick={() => openHistoryReport(report.id)}>
                      <span>{report.title}</span>
                      <span>{Math.round(report.credibility_score * 100)}%</span>
                    </button>
                  ))}
                  {reportHistory.length === 0 && <p className="empty-copy">暂无历史报告</p>}
                </article>
              </aside>
            </section>
          )}

          {activeSection === 'tasks' && (
            <section className="panel-card task-detail">
              <div className="panel-head">
                <h3>任务详情</h3>
                <span>流程可视化</span>
              </div>
              <ReviewGateBanner gate={reviewGate} />
              {showTimeline ? (
                <ProgramTimeline
                  current={currentPhase}
                  phases={phaseNodes}
                  onSelect={(phase) => setCurrentPhase(phase)}
                />
              ) : (
                <article className="panel-card empty-state">
                  <p className="stage-summary">阶段时间线将于预分析确认或收到流式输出后出现。</p>
                </article>
              )}
              <article className="panel-card pro-thinking-panel">
                <div className="panel-head">
                  <h3>Pro 思考中</h3>
                  <span>流式执行摘要</span>
                </div>
                {thinkingFeed.length ? (
                  <ul className="pro-thinking-list">
                    {thinkingFeed.map((log, idx) => (
                      <li key={`${log.ts}-${idx}`}>
                        <span className="pro-thinking-phase">{phaseTitleMap.get(log.phase) || log.phase}</span>
                        <div>
                          <p>{log.message}</p>
                          <small>{new Date(log.ts).toLocaleTimeString('zh-CN')}</small>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-copy">等待流式输出…</p>
                )}
              </article>
              <section className="stage-flow">
                {phaseNodes.map((phase) => {
                  const rawLogs = phaseLogs[phase.key] || []
                  const displayLogs =
                    phase.key === 'evidence'
                      ? buildEvidenceDisplayLogs(rawLogs)
                      : rawLogs.slice(0, 120).reverse()
                  return (
                    <div key={phase.key} ref={(el) => { phaseRefs.current[phase.key] = el }}>
                      <ProgramStageCard
                        title={phase.title}
                        status={phase.status}
                        summary={phase.summary}
                        actionHint={phase.actionHint}
                        collapsible
                        isOpen={openStages[phase.key]}
                        onToggle={() => setOpenStages((prev) => ({ ...prev, [phase.key]: !prev[phase.key] }))}
                      >
                        {phase.key === 'preview' && preview && (
                          <div className="stage-detail-block">
                            <p>意图摘要：{preview.intent_summary}</p>
                            <p>风险提示：{(preview.risk_notes || []).join('；') || '无'}</p>
                            <p>来源计划：{previewPlatforms.join('、') || '待确认'}</p>
                            {humanNotes && <p>人工补充：{humanNotes}</p>}
                          </div>
                        )}
                        {phase.key === 'evidence' && result?.no_data_explainer && (
                          <div className="stage-detail-block warning">
                            <p>空结果解释：{prettyReasonCode(result.no_data_explainer.reason_code)}</p>
                            <p>覆盖率：{Math.round(Number(result.no_data_explainer.coverage_ratio || 0) * 100)}%</p>
                            <p>尝试平台：{(result.no_data_explainer.attempted_platforms || []).join('、') || '无'}</p>
                            <p>建议补检：{(result.no_data_explainer.next_queries || []).slice(0, 3).join(' / ') || '无'}</p>
                          </div>
                        )}
                        {phase.key === 'verification' && result?.claim_analysis && (
                          <div className="stage-detail-block">
                            <p>主张结论：{String((result.claim_analysis as Record<string, unknown>).run_verdict || 'UNCERTAIN')}</p>
                            <p>待复核数量：{Array.isArray((result.claim_analysis as Record<string, unknown>).review_queue) ? ((result.claim_analysis as Record<string, unknown>).review_queue as unknown[])?.length : 0}</p>
                          </div>
                        )}
                        {phase.key === 'conclusion' && (
                          <div className="stage-detail-block conclusion">
                            <p className="conclusion-short">{shortConclusion(result)}</p>
                            <p className="conclusion-long">{longConclusion(result, freshnessText)}</p>
                            <div className="meta-row">
                              <span>截至时间：{freshness.as_of ? new Date(freshness.as_of).toLocaleString('zh-CN') : '--'}</span>
                              <span>新鲜度：{freshness.status}</span>
                            </div>
                          </div>
                        )}
                        <div className="stage-log-wrap">
                          <p className="hint-text">阶段日志</p>
                          {displayLogs.length ? (
                            <ul className="stage-logs" ref={phase.key === 'evidence' ? evidenceLogRef : undefined}>
                              {displayLogs.map((log, idx) => {
                                const evidenceMeta = log.type === 'evidence_found' ? getEvidenceMeta(log.payload) : null
                                const evidenceDetail = evidenceMeta
                                  ? [evidenceMeta.source, evidenceMeta.title || evidenceMeta.snippet]
                                      .filter(Boolean)
                                      .join(' · ')
                                  : ''
                                const evidenceText = evidenceMeta
                                  ? truncateText(evidenceDetail || evidenceMeta.url || '新证据')
                                  : ''
                                return (
                                  <li key={`${log.ts}-${idx}`}>
                                    <span>{new Date(log.ts).toLocaleTimeString('zh-CN')}</span>
                                    <div className="log-body">
                                      <strong>{log.message}</strong>
                                      {evidenceMeta && evidenceText && (
                                        evidenceMeta.url ? (
                                          <a
                                            className="evidence-link"
                                            href={evidenceMeta.url}
                                            target="_blank"
                                            rel="noreferrer"
                                          >
                                            {evidenceText}
                                          </a>
                                        ) : (
                                          <span className="evidence-link">{evidenceText}</span>
                                        )
                                      )}
                                    </div>
                                  </li>
                                )
                              })}
                            </ul>
                          ) : (
                            <p className="empty-copy">暂无阶段日志。</p>
                          )}
                        </div>
                      </ProgramStageCard>
                    </div>
                  )
                })}
              </section>
            </section>
          )}

          {activeSection === 'analysis' && (
            <section className="advanced-wrap panel-card">
              <div className="panel-head">
                <h3>分析中心</h3>
                <div className="head-inline">
                  <DynamicMark />
                  <button type="button" className="ghost-btn" onClick={() => setShowAdvanced((v) => !v)}>
                    {showAdvanced ? '收起' : '展开'}
                  </button>
                </div>
              </div>

              {showAdvanced ? (
                <>
                  <article className="sub-card compact-metrics">
                    <h4>证据结构快照</h4>
                    {summaryBars.map((row) => (
                      <div key={row.label} className="metric-row">
                        <span>{row.label}</span>
                        <strong>{row.value}</strong>
                        <em>{row.pct}%</em>
                      </div>
                    ))}
                  </article>
                  <AdvancedForensicsPanel result={result} />
                </>
              ) : (
                <p className="empty-copy">当前为简洁模式。点击“展开”查看证据卡、主张追踪、传播异常与可视化。</p>
              )}
            </section>
          )}

          {activeSection === 'conclusions' && (
            <section className="panel-card">
              <div className="panel-head">
                <h3>结论管理</h3>
                <span>发布与复核</span>
              </div>
              <ReviewGateBanner gate={reviewGate} />
              <article className="panel-card">
                <div className="panel-head">
                  <h4>结论摘要</h4>
                  <span>可信度与时效</span>
                </div>
                <p className="conclusion-short">{shortConclusion(result)}</p>
                <p className="conclusion-long">{longConclusion(result, freshnessText)}</p>
                <div className="meta-row">
                  <span>截至时间：{freshness.as_of ? new Date(freshness.as_of).toLocaleString('zh-CN') : '--'}</span>
                  <span>新鲜度：{freshness.status}</span>
                </div>
              </article>
              {renderPublishPanel('full')}
            </section>
          )}

          {activeSection === 'archives' && (
            <MyWorkspace
              result={result}
              reports={reportHistory}
              reviewTasks={reviewTasks}
              replayResult={replayResult}
              onCloseReviewTask={closeReviewTask}
              onOpenReport={openHistoryReport}
            />
          )}

          {activeSection === 'settings' && (
            <section className="panel-card diagnostics-panel">
              <div className="panel-head">
                <h3>系统设置</h3>
                <span>诊断与配置</span>
              </div>
              {result?.platform_health_snapshot && Object.keys(result.platform_health_snapshot).length > 0 ? (
                <div className="health-grid">
                  {Object.entries(result.platform_health_snapshot).slice(0, 12).map(([key, value]) => (
                    <div key={key} className="health-item">
                      <p>{key}</p>
                      <small>{typeof value === 'string' ? value : JSON.stringify(value)}</small>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-copy">暂无诊断数据，等待运行完成后展示。</p>
              )}
              <article className="sub-card">
                <div className="sub-head">
                  <h4>事件流统计</h4>
                  <span className="sub-meta">实时</span>
                </div>
                <p className="stage-summary">当前流事件：{streamEvents.length} 条</p>
              </article>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

export default App
