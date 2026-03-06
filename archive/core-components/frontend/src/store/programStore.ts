import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import type {
  InvestigationPreviewResponse,
  InvestigationRunResult,
  InvestigationStreamEvent,
  PublishSuggestionResponse,
  ReportResponse,
} from '../api'
import type { FreshnessState, LogItem, PhaseStatus, ProgramPhase, ReviewGateState } from '../types/runtime'

export interface PhaseNode {
  key: ProgramPhase
  title: string
  subtitle: string
  status: PhaseStatus
  summary: string
  actionHint: string
}

export interface ReviewTask {
  id: string
  runId: string
  createdAt: string
  priority: 'low' | 'medium' | 'high'
  reasons: string[]
  status: 'open' | 'closed'
}

interface ProgramState {
  activeNav: 'program' | 'my'
  runId: string
  runStatus: string
  preview: InvestigationPreviewResponse | null
  result: InvestigationRunResult | null
  streamEvents: InvestigationStreamEvent[]
  phaseLogs: Record<ProgramPhase, LogItem[]>
  awaitingHumanConfirm: boolean
  humanNotes: string
  humanConfirmedAt: string | null
  publishSuggestions: PublishSuggestionResponse | null
  phaseNodes: PhaseNode[]
  currentPhase: ProgramPhase
  freshness: FreshnessState
  reviewGate: ReviewGateState
  reviewTasks: ReviewTask[]
  reportHistory: ReportResponse[]
  setActiveNav: (nav: 'program' | 'my') => void
  setPreview: (preview: InvestigationPreviewResponse | null) => void
  setRunMeta: (meta: { runId: string; runStatus: string }) => void
  setResult: (result: InvestigationRunResult | null) => void
  pushStreamEvent: (event: InvestigationStreamEvent) => void
  pushPhaseLog: (phase: ProgramPhase, item: LogItem) => void
  setAwaitingHumanConfirm: (awaiting: boolean) => void
  setHumanNotes: (notes: string) => void
  setHumanConfirmedAt: (value: string | null) => void
  setPublishSuggestions: (payload: PublishSuggestionResponse | null) => void
  setPhaseStatus: (phase: ProgramPhase, patch: Partial<PhaseNode>) => void
  setCurrentPhase: (phase: ProgramPhase) => void
  setFreshness: (freshness: FreshnessState) => void
  setReviewGate: (reviewGate: ReviewGateState) => void
  addReviewTask: (task: Omit<ReviewTask, 'id' | 'createdAt' | 'status'>) => void
  closeReviewTask: (taskId: string) => void
  setReportHistory: (reports: ReportResponse[]) => void
  resetRun: () => void
}

const defaultPhases: PhaseNode[] = [
  { key: 'preview', title: '预分析阶段', subtitle: 'Intent Preview', status: 'pending', summary: '等待提交主张', actionHint: '完成预分析后需人工确认' },
  { key: 'evidence', title: '采集与证据阶段', subtitle: 'Evidence Acquisition', status: 'pending', summary: '尚未检索', actionHint: '系统将自动采集并评估证据质量' },
  { key: 'verification', title: '核验与冲突阶段', subtitle: 'Verification & Conflicts', status: 'pending', summary: '尚未核验', actionHint: '系统将进行主张级判定与冲突识别' },
  { key: 'conclusion', title: '结论阶段', subtitle: 'Verdict', status: 'pending', summary: '暂无结论', actionHint: '结论将附带时效与人工复核门控' },
]

const defaultFreshness: FreshnessState = {
  as_of: '',
  status: 'TIME_UNKNOWN',
  degraded: false,
}

const defaultReviewGate: ReviewGateState = {
  required: false,
  priority: 'low',
  reasons: [],
}

const defaultPhaseLogs: Record<ProgramPhase, LogItem[]> = {
  preview: [],
  evidence: [],
  verification: [],
  conclusion: [],
}

const REVIEW_TASKS_KEY = 'aletheia_review_tasks_v1'

function loadReviewTasks(): ReviewTask[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(REVIEW_TASKS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ReviewTask[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveReviewTasks(tasks: ReviewTask[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(REVIEW_TASKS_KEY, JSON.stringify(tasks.slice(0, 100)))
  } catch {
    // ignore persistence failures
  }
}

export const useProgramStore = create<ProgramState>()(
  devtools((set) => ({
    activeNav: 'program',
    runId: '',
    runStatus: 'idle',
    preview: null,
    result: null,
    streamEvents: [],
    phaseLogs: defaultPhaseLogs,
    awaitingHumanConfirm: false,
    humanNotes: '',
    humanConfirmedAt: null,
    publishSuggestions: null,
    phaseNodes: defaultPhases,
    currentPhase: 'preview',
    freshness: defaultFreshness,
    reviewGate: defaultReviewGate,
    reviewTasks: loadReviewTasks(),
    reportHistory: [],
    setActiveNav: (nav) => set({ activeNav: nav }),
    setPreview: (preview) => set({ preview }),
    setRunMeta: ({ runId, runStatus }) => set({ runId, runStatus }),
    setResult: (result) => set({ result }),
    pushStreamEvent: (event) =>
      set((state) => ({ streamEvents: [event, ...state.streamEvents].slice(0, 400) })),
    pushPhaseLog: (phase, item) =>
      set((state) => ({
        phaseLogs: {
          ...state.phaseLogs,
          [phase]: [item, ...(state.phaseLogs[phase] || [])].slice(0, 160),
        },
      })),
    setAwaitingHumanConfirm: (awaiting) => set({ awaitingHumanConfirm: awaiting }),
    setHumanNotes: (notes) => set({ humanNotes: notes }),
    setHumanConfirmedAt: (value) => set({ humanConfirmedAt: value }),
    setPublishSuggestions: (payload) => set({ publishSuggestions: payload }),
    setPhaseStatus: (phase, patch) =>
      set((state) => ({
        phaseNodes: state.phaseNodes.map((node) => (node.key === phase ? { ...node, ...patch } : node)),
      })),
    setCurrentPhase: (phase) => set({ currentPhase: phase }),
    setFreshness: (freshness) => set({ freshness }),
    setReviewGate: (reviewGate) => set({ reviewGate }),
    addReviewTask: ({ runId, priority, reasons }) =>
      set((state) => {
        const next: ReviewTask[] = [
          {
            id: `${runId}-${Date.now()}`,
            runId,
            createdAt: new Date().toISOString(),
            priority,
            reasons,
            status: 'open' as const,
          },
          ...state.reviewTasks,
        ].slice(0, 100)
        saveReviewTasks(next)
        return { reviewTasks: next }
      }),
    closeReviewTask: (taskId) =>
      set((state) => {
        const next = state.reviewTasks.map((task) =>
          task.id === taskId ? { ...task, status: 'closed' as const } : task
        )
        saveReviewTasks(next)
        return { reviewTasks: next }
      }),
    setReportHistory: (reports) => set({ reportHistory: reports }),
    resetRun: () =>
      set({
        runId: '',
        runStatus: 'idle',
        preview: null,
        result: null,
        streamEvents: [],
        phaseLogs: defaultPhaseLogs,
        awaitingHumanConfirm: false,
        humanNotes: '',
        humanConfirmedAt: null,
        publishSuggestions: null,
        phaseNodes: defaultPhases,
        currentPhase: 'preview',
        freshness: defaultFreshness,
        reviewGate: defaultReviewGate,
      }),
  }))
)

export function mapStepIdToPhase(stepId: string): ProgramPhase {
  const normalized = String(stepId || '').toLowerCase()
  if (['intent_preview', 'source_planning', 'network_precheck'].includes(normalized)) return 'preview'
  if (['multiplatform_search', 'external_sources'].includes(normalized)) return 'evidence'
  if (['cross_platform_credibility', 'multi_agent', 'claim_analysis', 'opinion_monitoring'].includes(normalized)) return 'verification'
  return 'conclusion'
}
