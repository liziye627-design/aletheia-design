export type WebMode = 'audit' | 'search' | 'report';

export interface EnhancedReasoningStep {
  stage: string;
  timestamp: string;
  reasoning: string;
  conclusion: string;
  confidence: number;
  evidence: string[];
  concerns: string[];
  score_impact: number;
}

export interface EnhancedReasoningChain {
  steps: EnhancedReasoningStep[];
  final_score: number;
  final_level: string;
  risk_flags: string[];
  total_confidence: number;
  processing_time_ms: number;
}

export interface EnhancedAnalyzeResponse {
  intel: Record<string, unknown> & {
    credibility_score?: number;
    credibility_level?: string;
    risk_flags?: string[];
    source_platform?: string;
  };
  reasoning_chain: EnhancedReasoningChain;
  processing_time_ms: number;
}

export interface MultiPlatformSearchResponse {
  success: boolean;
  keyword: string;
  data: Record<string, Array<Record<string, unknown>>>;
  total_posts: number;
  platform_count: number;
}

export interface CredibilityReport {
  keyword: string;
  timestamp: string;
  credibility_score: number;
  credibility_level: string;
  risk_flags?: string[];
  summary: {
    total_posts: number;
    total_engagement: number;
    avg_engagement: number;
    platform_count: number;
    new_account_ratio: number;
  };
  platform_stats?: Record<string, {
    post_count: number;
    total_likes: number;
    total_comments: number;
    total_shares: number;
    avg_engagement: number;
  }>;
  evidence_chain?: Array<{
    step: string;
    description: string;
    severity?: string;
  }>;
}

export interface CrossPlatformCredibilityResponse {
  success: boolean;
  data: CredibilityReport;
}
