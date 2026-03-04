/**
 * Aletheia Frontend Types
 * 统一的类型定义，消除 any 类型
 */

// ===== 分析相关类型 =====

export interface ReasoningStep {
  step: number;
  stage: string;
  reasoning: string;
  conclusion: string;
  confidence: number;
  evidence: string[];
  concerns: string[];
  score_impact: number;
}

export interface IntelData {
  id: string;
  content_text: string;
  source_platform: string;
  credibility_score: number;
  created_at: string;
}

export interface AnalysisResult {
  intel: IntelData;
  reasoning_chain: {
    steps: ReasoningStep[];
    final_score: number;
    final_level: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNCERTAIN';
    risk_flags: string[];
  };
}

// ===== 搜索相关类型 =====

export interface SearchResultItem {
  platform: string;
  title: string;
  content?: string;
  url?: string;
  author?: string;
  timestamp?: string;
  engagement?: {
    likes?: number;
    comments?: number;
    shares?: number;
  };
  evidence_quality?: 'high' | 'medium' | 'low' | 'unknown';
}

export interface PlatformStats {
  post_count: number;
  engagement_total: number;
}

export interface SearchResponse {
  search: {
    results: Record<string, SearchResultItem[]>;
  };
  aggregate?: {
    summary: {
      total_posts: number;
      platform_count: number;
      time_range: string;
    };
    platform_stats: Record<string, PlatformStats>;
  };
  agentData?: {
    overall_credibility: number;
    credibility_level: string;
    platform_results: Record<string, unknown>;
    synthesis?: {
      cross_platform_verification: string;
    };
  };
}

// ===== 组件 Props 类型 =====

export interface WeiboFeedCardProps {
  post: SearchResultItem & { llmAnalysis?: unknown };
  platform: string;
}

export interface StepTimelineProps {
  steps: ReasoningStep[];
  activeStepIndex: number;
  onStepClick: (index: number) => void;
}

export interface CredibilityBadgeProps {
  level: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNCERTAIN';
  score: number;
}

export interface EvidenceCardProps {
  source: {
    id: string;
    platform: string;
    title: string;
    url?: string;
    fetchMethod?: string;
    evidenceQuality?: string;
  };
}

// ===== 状态管理类型 =====

export interface AppState {
  // 分析状态
  analysisResult: AnalysisResult | null;
  isAnalyzing: boolean;
  
  // 搜索状态
  searchResult: SearchResponse | null;
  isSearching: boolean;
  
  // 历史记录
  historyItems: IntelData[];
  
  // 当前激活的标签
  activeTab: 'verify' | 'report' | 'search' | 'evidence';
  
  // Actions
  setAnalysisResult: (result: AnalysisResult | null) => void;
  setIsAnalyzing: (isAnalyzing: boolean) => void;
  setSearchResult: (result: SearchResponse | null) => void;
  setIsSearching: (isSearching: boolean) => void;
  setActiveTab: (tab: 'verify' | 'report' | 'search' | 'evidence') => void;
  addHistoryItem: (item: IntelData) => void;
}

// ===== API 类型 =====

export interface ApiError {
  message: string;
  code?: string;
  status?: number;
}

export type ApiResponse<T> = 
  | { success: true; data: T }
  | { success: false; error: ApiError };
