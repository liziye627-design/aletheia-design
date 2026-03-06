/**
 * Type definitions for Aletheia Mobile App
 */

// ==================== API Types ====================

export interface User {
  id: string;
  email: string;
  username: string;
  avatar?: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  username: string;
}

// ==================== Intel Types ====================

export interface IntelAnalyzeRequest {
  content: string;
  source_platform?: string;
  original_url?: string;
  image_urls?: string[];
  video_url?: string;
  metadata?: Record<string, any>;
}

export interface VerificationResult {
  passed: boolean;
  score: number;
  details: string;
  evidence?: string[];
}

export interface IntelResult {
  id: string;
  content: string;
  credibility_score: number;
  risk_tags: string[];
  reasoning_chain: ReasoningStep[];
  physics_verification?: VerificationResult;
  logic_verification?: VerificationResult;
  entropy_analysis?: {
    score: number;
    source_diversity: number;
    temporal_spread: number;
  };
  sources: SourceInfo[];
  created_at: string;
}

export interface ReasoningStep {
  step: number;
  type: 'observation' | 'hypothesis' | 'verification' | 'conclusion';
  content: string;
  confidence: number;
  evidence?: string[];
}

export interface SourceInfo {
  platform: string;
  url: string;
  author?: string;
  published_at?: string;
  credibility?: number;
}

export interface IntelAnalyzeResponse {
  intel: IntelResult;
  processing_time_ms: number;
}

// ==================== Feed Types ====================

export interface FeedItem {
  id: string;
  title: string;
  snippet: string;
  source: string;
  source_platform: string;
  published_at: string;
  credibility_score: number;
  risk_tags: string[];
  image_url?: string;
  url: string;
}

export interface FeedResponse {
  items: FeedItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// ==================== Report Types ====================

export interface Report {
  id: string;
  title: string;
  summary: string;
  content_html: string;
  credibility_score: number;
  created_at: string;
  updated_at: string;
  sources: SourceInfo[];
  tags: string[];
}

export interface ReportListResponse {
  items: Report[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// ==================== Trending Types ====================

export interface TrendingTopic {
  keyword: string;
  mention_count: number;
  platforms: string[];
  trend_score: number;
  sentiment: 'positive' | 'negative' | 'neutral';
  sample_content?: string;
}

export interface TrendingTopicsResponse {
  topics: TrendingTopic[];
  updated_at: number;
}

// ==================== Navigation Types ====================

export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
  IntelDetail: { intel_id: string };
  ReportDetail: { report_id: string };
  History: undefined;
  Search: undefined;
  Settings: undefined;
};

export type MainTabParamList = {
  Feeds: undefined;
  Reports: undefined;
  Profile: undefined;
};

// ==================== Store Types ====================

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

export interface FeedState {
  items: FeedItem[];
  isLoading: boolean;
  error: string | null;
  page: number;
  hasMore: boolean;
  fetchFeeds: (refresh?: boolean) => Promise<void>;
}

// ==================== Layered Verification Types ====================

export interface LayeredVerificationLayerResult {
  layer: 1 | 2 | 3 | 4;
  title: string;
  success: boolean;
  summary: string;
  confidence?: number;
  evidenceCount?: number;
}

export interface GeneratedArticleRecord {
  id: string;
  title: string;
  topic: string;
  kind: 'refute' | 'approve';
  credibility: number;
  content: string;
  createdAt: string;
  sources?: string[];
}

export type DocumentFormat = 'txt' | 'md' | 'html' | 'json' | 'pdf' | 'docx';

export interface DocumentArtifact {
  format: DocumentFormat;
  fileName: string;
  mimeType: string;
  content: string;
}
