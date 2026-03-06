const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

async function requestJson<T>(
  path: string,
  init: RequestInit,
  fallbackMessage: string
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'unknown error'
    throw new Error(`网络请求失败（${msg}）。请确认后端已启动：${API_BASE}`)
  }

  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.json()
      detail = payload?.detail || payload?.message || ''
    } catch {
      detail = await response.text()
    }
    throw new Error(detail || fallbackMessage)
  }

  return response.json() as Promise<T>
}

export type ToolMode = 'dual' | 'enhanced' | 'search'
export type ExportFormat = 'pdf' | 'docx' | 'md' | 'txt' | 'html' | 'json'

// ========== Intel Enhanced ==========

export interface AnalyzeRequest {
  content: string
  source_platform?: string
  original_url?: string
  image_urls?: string[]
  metadata?: Record<string, unknown>
}

export interface ReasoningStep {
  stage: string
  timestamp: string
  reasoning: string
  conclusion: string
  confidence: number
  evidence: string[]
  concerns: string[]
  score_impact: number
}

export interface ReasoningChain {
  steps: ReasoningStep[]
  final_score: number
  final_level: string
  risk_flags: string[]
  total_confidence: number
  processing_time_ms: number
}

export interface IntelData {
  id: string
  content_text: string
  source_platform?: string
  original_url?: string
  credibility_score?: number
  credibility_level?: string
  risk_flags?: string[]
  verification_status?: string
  created_at?: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

export interface AnalyzeResponse {
  intel: IntelData
  reasoning_chain: ReasoningChain
  processing_time_ms: number
}

// ========== Multi-platform ==========

export type RawPost = Record<string, unknown>

export interface MultiplatformSearchResponse {
  success: boolean
  keyword: string
  data: Record<string, RawPost[]>
  total_posts: number
  platform_count: number
}

export interface HotFocusItem {
  id: string
  title: string
  summary: string
  url: string
  published_at: string
  category: string
  source_name: string
  source_id: string
  group_name: string
  score: number
}

export interface HotFocusSection {
  category: string
  items: HotFocusItem[]
}

export interface HotFocusResponse {
  success: boolean
  updated_at: string
  expires_at?: string
  source_count: number
  candidate_count: number
  summary_items: HotFocusItem[]
  detail_items: HotFocusItem[]
  sections: HotFocusSection[]
}

export interface AggregateSummary {
  total_posts: number
  platform_count: number
  [key: string]: unknown
}

export interface PlatformAggregateStat {
  post_count: number
  avg_engagement: number
  [key: string]: unknown
}

export interface MultiplatformAggregateData {
  summary: AggregateSummary
  platform_stats: Record<string, PlatformAggregateStat>
  top_entities?: Array<{ entity: string; count: number }>
  time_distribution?: Record<string, number>
  raw_data?: Record<string, RawPost[]>
  [key: string]: unknown
}

export interface CrossPlatformAnomaly {
  type: string
  platform: string
  severity?: string
  description: string
  [key: string]: unknown
}

export interface CrossPlatformCredibilityData {
  keyword: string
  timestamp: string
  credibility_score: number
  credibility_level: string
  risk_flags: string[]
  summary: AggregateSummary
  platform_stats: Record<string, PlatformAggregateStat>
  anomalies: CrossPlatformAnomaly[]
  evidence_chain: Array<{ step: string; description: string }>
  top_entities?: Array<{ entity: string; count: number }>
  time_distribution?: Record<string, number>
  [key: string]: unknown
}

export interface PlatformSmallModelAnalysis {
  credibility_score?: number
  summary?: string
  risk_flags?: string[]
  [key: string]: unknown
}

export interface MultiAgentPlatformResult {
  raw_data?: RawPost[]
  small_model_analysis?: PlatformSmallModelAnalysis
  agent_metadata?: Record<string, unknown>
  [key: string]: unknown
}

export interface MultiAgentSynthesis {
  overall_credibility?: number
  credibility_level?: string
  risk_flags?: string[]
  recommendation?: string
  [key: string]: unknown
}


export interface DebateAnalysisData {
  claim: string
  keyword: string
  timestamp: string
  debate_process: {
    proponent: {
      stance: string
      main_arguments: Array<{
        claim: string
        evidence_ids: string[]
        reasoning: string
        strength?: number
      }>
      confidence?: number
      key_sources?: string[]
    }
    opponent: {
      stance: string
      main_arguments: Array<{
        claim: string
        evidence_ids: string[]
        reasoning: string
        weakness_type?: string
      }>
      risk_level?: number
      critical_issues?: string[]
    }
    judge: {
      final_verdict: string
      credibility_score: number
      reasoning_summary: string
      key_findings: Array<{
        finding: string
        evidence_support: string[]
        confidence: number
      }>
      recommendation?: string
    }
  }
  final_conclusion: {
    verdict: string
    credibility_score: number
    reasoning_summary: string
    key_findings: any[]
    recommendation: string
  }
  evidence_used: number
  unresolved_questions: string[]
}

export interface CotThinkingChainData {
  thinking_chain: {
    phase1_evidence_review: {
      title: string
      description: string
      evidence_count: number
    }
    phase2_proponent_analysis: {
      title: string
      description: string
      arguments: any[]
      confidence: number
      key_sources: string[]
    }
    phase3_opponent_analysis: {
      title: string
      description: string
      arguments: any[]
      risk_level: number
      critical_issues: string[]
    }
    phase4_judge_synthesis: {
      title: string
      description: string
      verdict: string
      credibility_score: number
      key_findings: any[]
      recommendation: string
    }
  }
  final_conclusion: any
  unresolved_questions: string[]
}

export interface MultiAgentAnalyzeData {
  debate_analysis?: DebateAnalysisData
  cot_thinking_chain?: CotThinkingChainData
  keyword: string
  platform_results: Record<string, MultiAgentPlatformResult>
  synthesis: MultiAgentSynthesis
  overall_credibility: number
  credibility_level: string
  risk_flags: string[]
  consensus_points: string[]
  conflicts: string[]
  recommendation: string
  evidence_summary?: Record<string, unknown>
  score_breakdown?: Record<string, unknown>
  generated_article?: {
    title?: string
    lead?: string
    body_markdown?: string
    highlights?: string[]
    insufficient_evidence?: string[]
    // 新增：双层结论结构
    public_verdict?: {
      headline: string
      explain: string
      label: 'VERIFIED' | 'LIKELY_TRUE' | 'UNCERTAIN' | 'LIKELY_FALSE' | 'FABRICATED'
      confidence: number
      as_of: string
    }
    // 新增：可核查动作列表
    reader_checklist?: Array<{
      claim_point: string
      status: 'SUPPORTED' | 'REFUTED' | 'UNCLEAR' | 'UNVERIFIED'
      how_to_check: string
      source_hint: string
      url?: string
    }>
    // 新增：证据边界
    evidence_boundary?: {
      well_supported: string[]
      insufficient: string[]
      conflicting: string[]
    }
    // 新增：时效性
    freshness?: {
      as_of: string
      latest_evidence_at?: string
      hours_old?: number
      status: 'FRESH' | 'RECENT' | 'STALE' | 'TIME_UNKNOWN'
      degraded: boolean
    }
    // 新增：人审触发
    human_review?: {
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
  } | string
  platform_errors?: Record<string, string[]>
  no_data_explainer?: {
    reason_code?: string
    reason_text?: string
    attempted_platforms?: string[]
    platform_errors?: Record<string, string[]>
    retrieval_scope?: Record<string, unknown>
    coverage_ratio?: number
    hit_count?: number
    retrievable_count?: number
    suggested_queries?: string[]
    next_queries?: string[]
  }
  processing_time_ms?: number
  timestamp?: string
  [key: string]: unknown
}

export interface PlaywrightRenderedExtractRequest {
  url: string
  critical_selector?: string
  schema?: Record<string, Record<string, unknown>>
  api_url_keyword?: string
  max_api_items?: number
  visible_text_limit?: number
  html_limit?: number
  headless?: boolean
  storage_state_path?: string
}

export interface PlaywrightRenderedExtractDiagnostics {
  critical_selector_found: boolean
  playwright_networkidle_reached: boolean
  custom_network_quiet_reached: boolean
  dom_stable: boolean
  scroll_count: number
  requests_seen: number
  [key: string]: unknown
}

export interface PlaywrightRenderedExtractData {
  success: boolean
  url: string
  captured_at: string
  diagnostics: PlaywrightRenderedExtractDiagnostics
  fields: Record<string, unknown>
  visible_text: string
  visible_text_truncated: boolean
  html: string
  html_truncated: boolean
  api_responses: Array<{
    url: string
    status: number
    payload: unknown
  }>
}

// ========== Reports ==========

export interface ReportResponse {
  id: string
  title: string
  summary: string
  content_html: string
  credibility_score: number
  status?: string
  created_at: string
  updated_at: string
  sources: Array<Record<string, unknown>>
  tags: string[]
}

export interface ReportListResponse {
  items: ReportResponse[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface ReportExportResponse {
  file_name: string
  mime_type: string
  content_base64: string
}

// ========== Investigations ==========

export type InvestigationMode = 'dual' | 'enhanced' | 'search'
export type AudienceProfile = 'tog' | 'tob' | 'both'

export interface InvestigationPreviewRequest {
  claim: string
  keyword?: string
  source_url?: string
  sourceUrl?: string
  platforms?: string[]
  mode?: InvestigationMode
  source_strategy?: 'auto' | 'stable_mixed_v1' | 'full'
}

export interface PreviewClaimDraft {
  claim_id: string
  text: string
  type: string
  confidence: number
  editable: boolean
}

export interface InvestigationPreviewResponse {
  preview_id: string
  status: 'ready' | 'degraded'
  intent_summary: string
  event_type: string
  domain: string
  claims_draft: PreviewClaimDraft[]
  source_plan: Record<string, unknown>
  risk_notes: string[]
  fallback_reason?: string
  expires_at: string
}

export interface InvestigationRunRequest {
  claim: string
  keyword?: string
  source_url?: string
  sourceUrl?: string
  human_notes?: string
  humanNotes?: string
  platforms?: string[]
  mode?: InvestigationMode
  audience_profile?: AudienceProfile
  confirmed_preview_id?: string
  confirmed_claims?: string[]
  confirmed_platforms?: string[]
  enable_opinion_monitoring?: boolean
}

export interface InvestigationRunAccepted {
  run_id: string
  accepted_at: string
  initial_status: string
}

export interface InvestigationStreamEvent {
  id?: string
  type: string
  payload: Record<string, unknown>
}

export interface InvestigationRunResult {
  run_id: string
  status: string
  accepted_at?: string
  updated_at?: string
  completed_at?: string
  duration_sec?: number
  steps?: Array<Record<string, unknown>>
  error?: string
  search?: Record<string, unknown>
  source_plan?: Record<string, unknown>
  acquisition_report?: Record<string, unknown>
  claim_analysis?: Record<string, unknown>
  opinion_monitoring?: Record<string, unknown>
  no_data_explainer?: {
    reason_code?: string
    attempted_platforms?: string[]
    platform_errors?: Record<string, unknown>
    retrieval_scope?: Record<string, unknown>
    coverage_ratio?: number
    next_queries?: string[]
  }
  report_sections?: Array<Record<string, unknown>>
  step_summaries?: Array<Record<string, unknown>>
  dual_profile_result?: Record<string, unknown>
  score_breakdown?: Record<string, unknown>
  platform_health_snapshot?: Record<string, unknown>
  [key: string]: unknown
}

export interface PublishSuggestionItem {
  title: string
  text: string
  hashtags?: string[]
  angle?: string
}

export interface PublishSuggestionResponse {
  tweet_suggestions: PublishSuggestionItem[]
  mindmap_mermaid: string
  creative_directions: string[]
  hotspot_benefits: string[]
  generated_at?: string
}

export interface InsightMindmapResponse {
  root_topic: string
  mindmap_structure: Array<Record<string, unknown>>
  uncovered_directions: string[]
  mindmap_mermaid: string
  generated_at?: string
}

export interface InsightCommonAnalysis {
  generated_at?: string
  topic_analysis?: Record<string, unknown>
  structure_analysis?: Record<string, unknown>
  spread_analysis?: Record<string, unknown>
  source_analysis?: Record<string, unknown>
  audience_analysis?: Record<string, unknown>
  summary?: string
}

export interface InsightValueInsights {
  potential_value_insights: Array<Record<string, unknown>>
  mining_summary?: string
  generated_at?: string
}

export interface InsightArticleResponse {
  article_id: string
  title: string
  content: string
  template_type?: string
  platform?: string
  references?: Array<Record<string, unknown>>
  generated_at?: string
}

export interface GeoScanResponse {
  scan_id: string
  topic: string
  platforms: string[]
  content_items: Array<Record<string, unknown>>
  source_rankings: Array<Record<string, unknown>>
  ai_citation_samples: Array<Record<string, unknown>>
  generated_at?: string
  mindmap?: Record<string, unknown>
}

export interface GeoOpportunitiesResponse {
  topic: string
  opportunities: Array<Record<string, unknown>>
  generated_at?: string
}

export interface GeoContentResponse {
  content_id: string
  title: string
  content: string
  schema_markup?: string
  generated_at?: string
}

export async function analyzeEnhanced(
  request: AnalyzeRequest,
  signal?: AbortSignal
): Promise<AnalyzeResponse> {
  return requestJson<AnalyzeResponse>(
    '/intel/enhanced/analyze/enhanced',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    },
    '增强核验失败'
  )
}

export async function enhancedVerification(
  content: string,
  imageUrls?: string[],
  metadata?: Record<string, unknown>,
  signal?: AbortSignal
): Promise<AnalyzeResponse> {
  return analyzeEnhanced(
    {
      content,
      source_platform: 'web',
      image_urls: imageUrls,
      metadata: {
        mode: 'enhanced',
        generated_at: new Date().toISOString(),
        ...(metadata ?? {}),
      },
    },
    signal
  )
}

export async function searchMultiplatform(
  keyword: string,
  platforms?: string[],
  limitPerPlatform = 25,
  signal?: AbortSignal
): Promise<MultiplatformSearchResponse> {
  return requestJson<MultiplatformSearchResponse>(
    '/multiplatform/search',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        keyword,
        platforms,
        limit_per_platform: limitPerPlatform,
      }),
      signal,
    },
    '跨平台搜索失败'
  )
}

export async function fetchHotFocus(
  refresh = false,
  signal?: AbortSignal
): Promise<HotFocusResponse> {
  return requestJson<HotFocusResponse>(
    '/multiplatform/hot-focus',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh,
      }),
      signal,
    },
    '今日传播重点获取失败'
  )
}

export async function aggregateMultiplatform(
  keyword: string,
  platforms?: string[],
  limitPerPlatform = 40,
  signal?: AbortSignal
): Promise<MultiplatformAggregateData> {
  const payload = await requestJson<
    { success: boolean; data: MultiplatformAggregateData } | MultiplatformAggregateData
  >(
    '/multiplatform/aggregate',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        keyword,
        platforms,
        limit_per_platform: limitPerPlatform,
      }),
      signal,
    },
    '跨平台聚合失败'
  )
  if (typeof payload === 'object' && payload !== null && 'data' in payload) {
    return (payload as { data: MultiplatformAggregateData }).data
  }
  return payload
}

export async function analyzeCredibility(
  keyword: string,
  platforms?: string[],
  limitPerPlatform = 30,
  signal?: AbortSignal
): Promise<CrossPlatformCredibilityData> {
  const payload = await requestJson<
    { success: boolean; data: CrossPlatformCredibilityData } | CrossPlatformCredibilityData
  >(
    '/multiplatform/analyze-credibility',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        keyword,
        platforms,
        limit_per_platform: limitPerPlatform,
      }),
      signal,
    },
    '跨平台可信度分析失败'
  )
  if (typeof payload === 'object' && payload !== null && 'data' in payload) {
    return (payload as { data: CrossPlatformCredibilityData }).data
  }
  return payload
}

export async function multiAgentAnalyze(
  keyword: string,
  platforms?: string[],
  signal?: AbortSignal
): Promise<MultiAgentAnalyzeData> {
  const payload = await requestJson<
    { success: boolean; data: MultiAgentAnalyzeData } | MultiAgentAnalyzeData
  >(
    '/multiplatform/multi-agent-analyze',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        keyword,
        platforms,
        limit_per_platform: 16,
        collection_rounds: 3,
        round_interval_sec: 1,
      }),
      signal,
    },
    '多Agent分析失败'
  )
  if (typeof payload === 'object' && payload !== null && 'data' in payload) {
    return (payload as { data: MultiAgentAnalyzeData }).data
  }
  return payload
}

export async function playwrightRenderedExtract(
  request: PlaywrightRenderedExtractRequest,
  signal?: AbortSignal
): Promise<PlaywrightRenderedExtractData> {
  return requestJson<PlaywrightRenderedExtractData>(
    '/multiplatform/playwright-rendered-extract',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: request.url,
        critical_selector: request.critical_selector,
        schema: request.schema ?? {},
        api_url_keyword: request.api_url_keyword ?? '',
        max_api_items: request.max_api_items ?? 30,
        visible_text_limit: request.visible_text_limit ?? 18000,
        html_limit: request.html_limit ?? 250000,
        headless: request.headless ?? true,
        storage_state_path: request.storage_state_path,
      }),
      signal,
    },
    '渲染后页面抽取失败'
  )
}

export async function generateReport(
  input: {
    title: string
    content: string
    credibilityScore?: number
    tags?: string[]
    sources?: Array<Record<string, unknown>>
  },
  signal?: AbortSignal
): Promise<ReportResponse> {
  return requestJson<ReportResponse>(
    '/reports/generate',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title: input.title,
        content: input.content,
        credibility_score: input.credibilityScore ?? 0.5,
        tags: input.tags ?? [],
        sources: input.sources ?? [],
      }),
      signal,
    },
    '报告生成失败'
  )
}

export async function listReports(
  page = 1,
  pageSize = 20,
  signal?: AbortSignal
): Promise<ReportListResponse> {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return requestJson<ReportListResponse>(
    `/reports/?${query.toString()}`,
    {
      method: 'GET',
      signal,
    },
    '报告列表获取失败'
  )
}

export async function getReportById(reportId: string, signal?: AbortSignal): Promise<ReportResponse> {
  return requestJson<ReportResponse>(
    `/reports/${encodeURIComponent(reportId)}`,
    {
      method: 'GET',
      signal,
    },
    '报告详情获取失败'
  )
}

export async function exportReport(
  format: ExportFormat,
  payload: Record<string, unknown>,
  signal?: AbortSignal
): Promise<ReportExportResponse> {
  return requestJson<ReportExportResponse>(
    '/reports/export',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        format,
        payload,
      }),
      signal,
    },
    '报告导出失败'
  )
}

export async function previewInvestigation(
  request: InvestigationPreviewRequest,
  signal?: AbortSignal
): Promise<InvestigationPreviewResponse> {
  const { sourceUrl, ...rest } = request
  const normalizedRequest = {
    ...rest,
    source_url: request.source_url || sourceUrl,
  }
  return requestJson<InvestigationPreviewResponse>(
    '/investigations/preview',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'dual',
        source_strategy: 'auto',
        ...normalizedRequest,
      }),
      signal,
    },
    '预分析失败'
  )
}

export async function runInvestigation(
  request: InvestigationRunRequest,
  signal?: AbortSignal
): Promise<InvestigationRunAccepted> {
  const { sourceUrl, humanNotes, ...rest } = request
  const normalizedRequest = {
    ...rest,
    source_url: request.source_url || sourceUrl,
    human_notes: request.human_notes || humanNotes,
  }
  return requestJson<InvestigationRunAccepted>(
    '/investigations/run',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'dual',
        audience_profile: 'both',
        ...normalizedRequest,
      }),
      signal,
    },
    '任务启动失败'
  )
}

export async function getInvestigationResult(
  runId: string,
  signal?: AbortSignal
): Promise<InvestigationRunResult> {
  return requestJson<InvestigationRunResult>(
    `/investigations/${encodeURIComponent(runId)}`,
    {
      method: 'GET',
      signal,
    },
    '任务结果获取失败'
  )
}

export async function generatePublishSuggestions(
  runId: string,
  signal?: AbortSignal
): Promise<PublishSuggestionResponse> {
  return requestJson<PublishSuggestionResponse>(
    `/investigations/${encodeURIComponent(runId)}/publish/suggestions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    '发布建议生成失败'
  )
}

export async function generateGeoReport(
  runId: string,
  signal?: AbortSignal
): Promise<ReportResponse> {
  return requestJson<ReportResponse>(
    `/investigations/${encodeURIComponent(runId)}/publish/geo-report`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    'GEO 报告生成失败'
  )
}

export async function generateInsightMindmap(
  runId: string,
  signal?: AbortSignal
): Promise<InsightMindmapResponse> {
  return requestJson<InsightMindmapResponse>(
    `/investigations/${encodeURIComponent(runId)}/mindmap`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    '思维导图生成失败'
  )
}

export async function generateCommonAnalysis(
  runId: string,
  signal?: AbortSignal
): Promise<InsightCommonAnalysis> {
  return requestJson<InsightCommonAnalysis>(
    `/investigations/${encodeURIComponent(runId)}/analysis/common`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    '共性分析生成失败'
  )
}

export async function generateValueInsights(
  runId: string,
  signal?: AbortSignal
): Promise<InsightValueInsights> {
  return requestJson<InsightValueInsights>(
    `/investigations/${encodeURIComponent(runId)}/value-insights`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    '价值洞察生成失败'
  )
}

export async function generateInsightArticle(
  runId: string,
  payload: { value_direction?: string; template_type?: string; platform?: string },
  signal?: AbortSignal
): Promise<InsightArticleResponse> {
  return requestJson<InsightArticleResponse>(
    `/investigations/${encodeURIComponent(runId)}/generate-article`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
    '推文/文章生成失败'
  )
}

export async function geoScan(
  payload: { topic: string; platforms?: string[]; limit_per_platform?: number },
  signal?: AbortSignal
): Promise<GeoScanResponse> {
  return requestJson<GeoScanResponse>(
    '/geo/scan',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
    'GEO 扫描失败'
  )
}

export async function geoMindmap(
  scanId: string,
  signal?: AbortSignal
): Promise<InsightMindmapResponse> {
  return requestJson<InsightMindmapResponse>(
    `/geo/scan/${encodeURIComponent(scanId)}/mindmap`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    'GEO 思维导图生成失败'
  )
}

export async function geoOpportunities(
  scanId: string,
  signal?: AbortSignal
): Promise<GeoOpportunitiesResponse> {
  return requestJson<GeoOpportunitiesResponse>(
    `/geo/scan/${encodeURIComponent(scanId)}/opportunities`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    'GEO 机会挖掘失败'
  )
}

export async function geoGenerateContent(
  scanId: string,
  payload: { opportunity_id?: string; direction?: string },
  signal?: AbortSignal
): Promise<GeoContentResponse> {
  return requestJson<GeoContentResponse>(
    `/geo/scan/${encodeURIComponent(scanId)}/generate-content`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
    'GEO 内容生成失败'
  )
}

export async function geoMetrics(
  scanId: string,
  signal?: AbortSignal
): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(
    `/geo/scan/${encodeURIComponent(scanId)}/metrics`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    'GEO 监测指标获取失败'
  )
}

export async function dualModeAnalysis(
  content: string,
  keyword: string,
  platforms?: string[],
  signal?: AbortSignal
): Promise<{
  analysis: AnalyzeResponse
  search: MultiplatformSearchResponse
  aggregate: MultiplatformAggregateData
  credibility: CrossPlatformCredibilityData
}> {
  const [analysis, search, aggregate, credibility] = await Promise.all([
    enhancedVerification(content, undefined, { mode: 'dual' }, signal),
    searchMultiplatform(keyword, platforms, 25, signal),
    aggregateMultiplatform(keyword, platforms, 35, signal),
    analyzeCredibility(keyword, platforms, 25, signal),
  ])
  return { analysis, search, aggregate, credibility }
}

export async function multiSourceSearch(
  keyword: string,
  platforms?: string[],
  signal?: AbortSignal
): Promise<{
  search: MultiplatformSearchResponse
  aggregate: MultiplatformAggregateData
}> {
  const [search, aggregate] = await Promise.all([
    searchMultiplatform(keyword, platforms, 25, signal),
    aggregateMultiplatform(keyword, platforms, 40, signal),
  ])
  return { search, aggregate }
}

// ========== Evidence Library API ==========

export interface EvidenceSearchRequest {
  query: string
  fields?: string[]
  source_domains?: string[]
  platforms?: string[]
  source_tiers?: string[]
  authors?: string[]
  tags?: string[]
  publish_time_start?: string
  publish_time_end?: string
  min_evidence_score?: number
  exclude_deleted?: boolean
  size?: number
  offset?: number
  sort_by?: string
  sort_order?: string
  highlight?: boolean
  vector?: number[]
}

export interface EvidenceDocument {
  doc_id: string
  title: string
  content_text?: string
  canonical_url?: string
  original_url: string
  platform: string
  source_domain: string
  source_tier: string
  evidence_score: number
  publish_time?: string
  crawl_time: string
  extraction_method: string
  extraction_confidence: number
  version_id?: string
  version_count?: number
  has_corrections?: boolean
  _score?: number
  _highlight?: Record<string, string[]>
}

export interface EvidenceSearchResponse {
  total: number
  hits: EvidenceDocument[]
  took_ms: number
  query: Record<string, unknown>
  aggregations?: Record<string, unknown>
}

export interface EvidenceStatsResponse {
  total_documents: number
  total_versions: number
  total_search_hits: number
  by_platform: Record<string, number>
  by_source_tier: Record<string, number>
  by_extraction_method: Record<string, number>
  avg_evidence_score: number
  index_size_mb: number
  last_updated: string
  error?: string
}

export interface SimilarEvidenceRequest {
  doc_id?: string
  text?: string
  vector?: number[]
  k?: number
  exclude_self?: boolean
}

export interface BulkIndexResponse {
  indexed: number
  errors: Array<Record<string, unknown>>
}

/**
 * 搜索证据文档
 */
export async function searchEvidence(
  request: EvidenceSearchRequest,
  signal?: AbortSignal
): Promise<EvidenceSearchResponse> {
  return requestJson<EvidenceSearchResponse>(
    '/evidence/v1/search',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: request.query,
        fields: request.fields || ['title', 'content_text'],
        source_domains: request.source_domains || [],
        platforms: request.platforms || [],
        source_tiers: request.source_tiers || [],
        min_evidence_score: request.min_evidence_score,
        exclude_deleted: request.exclude_deleted ?? true,
        size: request.size || 20,
        offset: request.offset || 0,
        sort_by: request.sort_by || 'evidence_score',
        sort_order: request.sort_order || 'desc',
        highlight: request.highlight ?? true,
        vector: request.vector,
      }),
      signal,
    },
    '证据搜索失败'
  )
}

/**
 * 获取相似证据文档
 */
export async function findSimilarEvidence(
  request: SimilarEvidenceRequest,
  signal?: AbortSignal
): Promise<EvidenceSearchResponse> {
  return requestJson<EvidenceSearchResponse>(
    '/evidence/v1/similar',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: request.doc_id,
        text: request.text,
        vector: request.vector,
        k: request.k || 10,
        exclude_self: request.exclude_self ?? true,
      }),
      signal,
    },
    '相似证据检索失败'
  )
}

/**
 * 获取单个证据文档详情
 */
export async function getEvidenceDocument(
  docId: string,
  includeVersionChain = true,
  signal?: AbortSignal
): Promise<EvidenceDocument> {
  return requestJson<EvidenceDocument>(
    `/evidence/v1/doc/${encodeURIComponent(docId)}?include_version_chain=${includeVersionChain}`,
    {
      method: 'GET',
      signal,
    },
    '获取证据文档失败'
  )
}

/**
 * 获取证据库统计信息
 */
export async function getEvidenceStats(
  signal?: AbortSignal
): Promise<EvidenceStatsResponse> {
  return requestJson<EvidenceStatsResponse>(
    '/evidence/v1/stats',
    {
      method: 'GET',
      signal,
    },
    '获取证据库统计失败'
  )
}

/**
 * 批量索引证据文档
 */
export async function bulkIndexEvidence(
  documents: Array<Record<string, unknown>>,
  signal?: AbortSignal
): Promise<BulkIndexResponse> {
  return requestJson<BulkIndexResponse>(
    '/evidence/v1/bulk',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ documents }),
      signal,
    },
    '批量索引失败'
  )
}

/**
 * 索引单个证据文档
 */
export async function indexEvidenceDocument(
  document: Record<string, unknown>,
  signal?: AbortSignal
): Promise<{ status: string; doc_id: string }> {
  return requestJson<{ status: string; doc_id: string }>(
    '/evidence/v1/index',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(document),
      signal,
    },
    '索引证据文档失败'
  )
}

/**
 * 初始化OpenSearch索引
 */
export async function initEvidenceIndexes(
  signal?: AbortSignal
): Promise<{ status: string; message: string; indexes: string[] }> {
  return requestJson<{ status: string; message: string; indexes: string[] }>(
    '/evidence/v1/init',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
    '初始化索引失败'
  )
}

/**
 * 检查证据服务健康状态
 */
export async function checkEvidenceHealth(
  signal?: AbortSignal
): Promise<{
  status: string
  service: string
  opensearch: string
  document_count?: number
  timestamp: string
  error?: string
}> {
  return requestJson<{
    status: string
    service: string
    opensearch: string
    document_count?: number
    timestamp: string
    error?: string
  }>(
    '/evidence/v1/health',
    {
      method: 'GET',
      signal,
    },
    '证据服务健康检查失败'
  )
}

/**
 * 获取发现层搜索命中记录
 */
export async function getDiscoveryHits(
  queryId: string,
  platform?: string,
  signal?: AbortSignal
): Promise<{
  query_id: string
  query: string
  total: number
  hits: Array<Record<string, unknown>>
  captured_at: string
}> {
  const params = new URLSearchParams()
  if (platform) {
    params.append('platform', platform)
  }
  const queryString = params.toString() ? `?${params.toString()}` : ''

  return requestJson<{
    query_id: string
    query: string
    total: number
    hits: Array<Record<string, unknown>>
    captured_at: string
  }>(
    `/evidence/v1/hits/${encodeURIComponent(queryId)}${queryString}`,
    {
      method: 'GET',
      signal,
    },
    '获取发现层记录失败'
  )
}
