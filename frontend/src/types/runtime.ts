import type {
  AnalyzeResponse,
  CrossPlatformCredibilityData,
  MultiAgentAnalyzeData,
  MultiplatformAggregateData,
  MultiplatformSearchResponse,
  PlaywrightRenderedExtractData,
  ReportResponse,
  ReasoningStep,
} from '../api'

export type RunStatus = 'idle' | 'running' | 'completed' | 'failed'
export type FeedLevel = 'info' | 'success' | 'warning' | 'error'
export type StreamStepStatus = 'pending' | 'streaming' | 'done'

export interface FeedEvent {
  id: string
  time: string
  source: string
  level: FeedLevel
  message: string
}

export interface StreamedReasoningStep extends ReasoningStep {
  index: number
  status: StreamStepStatus
  streamedReasoning: string
  streamedConclusion: string
}

export interface NormalizedSearchPost {
  id: string
  platform: string
  title: string
  content: string
  author: string
  timestamp?: string
  url?: string
  engagement: {
    likes: number
    comments: number
    shares: number
  }
  credibilityScore?: number
}

// ===== 双层结论结构 =====
export interface PublicVerdict {
  headline: string        // 30-45 字短结论
  explain: string         // 90-130 字解释段
  label: 'VERIFIED' | 'LIKELY_TRUE' | 'UNCERTAIN' | 'LIKELY_FALSE' | 'FABRICATED'
  confidence: number
  as_of: string
}

// ===== 可核查动作 =====
export interface ReaderCheckItem {
  claim_point: string
  status: 'SUPPORTED' | 'REFUTED' | 'UNCLEAR' | 'UNVERIFIED'
  how_to_check: string    // 读者可执行的验证步骤
  source_hint: string     // 去哪里查
  url?: string
}

// ===== 证据边界 =====
export interface EvidenceBoundary {
  well_supported: string[]
  insufficient: string[]
  conflicting: string[]
}

// ===== 时效性状态 =====
export interface FreshnessState {
  as_of: string
  latest_evidence_at?: string
  hours_old?: number
  status: 'FRESH' | 'RECENT' | 'STALE' | 'TIME_UNKNOWN'
  degraded: boolean
}

// ===== 人审触发 =====
export interface HumanReviewState {
  required: boolean
  priority: 'LOW' | 'NORMAL' | 'MEDIUM' | 'HIGH'
  reasons: string[]
  handoff_packet?: {
    claim: string
    key_evidence: string[]
    conflicts: string[]
    insufficient: string[]
    recommended_action: string
  }
}

// ===== 空结果解释 =====
export interface NoDataExplainer {
  reason_code: 'FALLBACK_EMPTY' | 'NETWORK_UNREACHABLE' | 'MEDIACRAWLER_LOGIN_REQUIRED' | 'INSUFFICIENT_EVIDENCE' | 'TIMEOUT'
  reason_text: string
  attempted_platforms: string[]
  hit_count: number
  retrievable_count: number
  coverage_ratio: number
  failed_platforms: Record<string, string>
  suggested_queries: string[]
}

export interface VerificationRunState {
  runId: string
  claim: string
  keyword: string
  sourceUrl?: string
  mode: 'dual' | 'enhanced' | 'search'
  platforms: string[]
  startedAt: string
  finishedAt?: string
  status: RunStatus
  activeStepIndex: number
  streamSteps: StreamedReasoningStep[]
  feed: FeedEvent[]
  analysis?: AnalyzeResponse
  search?: MultiplatformSearchResponse
  aggregate?: MultiplatformAggregateData
  credibility?: CrossPlatformCredibilityData
  multiAgent?: MultiAgentAnalyzeData
  renderedExtract?: PlaywrightRenderedExtractData
  generatedReport?: ReportResponse
  generatedNarrative?: string
  errorMessage?: string

  // 新增字段（兼容旧数据）
  public_verdict?: PublicVerdict
  reader_checklist?: ReaderCheckItem[]
  evidence_boundary?: EvidenceBoundary
  freshness?: FreshnessState
  human_review?: HumanReviewState
  no_data_explainer?: NoDataExplainer
}

// ===== New Program UI Runtime Types =====
export type ProgramPhase = 'preview' | 'evidence' | 'verification' | 'conclusion'
export type PhaseStatus = 'pending' | 'running' | 'partial' | 'done' | 'error'

export interface LogItem {
  ts: string
  type: string
  message: string
  payload?: Record<string, unknown>
}

// 兼容旧类型导出
export type { FreshnessState as FreshnessStateOld }
export type { ReviewGateState as ReviewGateStateOld }

export interface ReviewGateState {
  required: boolean
  priority: 'low' | 'medium' | 'high'
  reasons: string[]
}
