/**
 * Layered Verification Service
 * 分层核验：每一层独立调用后端接口
 */

import apiClient from './api';
import { API_CONFIG } from './config';

export interface EnhancedAnalyzeResponse {
  intel?: {
    credibility_score?: number;
    credibility_level?: string;
    risk_flags?: string[];
  };
  reasoning_chain?: {
    steps?: Array<{
      stage?: string;
      conclusion?: string;
      confidence?: number;
      evidence?: string[];
    }>;
    final_score?: number;
  };
  processing_time_ms?: number;
}

export interface MultiPlatformSearchResponse {
  success: boolean;
  keyword?: string;
  data?: Record<string, Array<Record<string, unknown>>>;
  total_posts?: number;
  platform_count?: number;
}

export interface CredibilityReportResponse {
  success: boolean;
  data?: {
    credibility_score?: number;
    credibility_level?: string;
    risk_flags?: string[];
    evidence_chain?: Array<{
      step?: string;
      description?: string;
      severity?: string;
    }>;
    summary?: {
      total_posts?: number;
      platform_count?: number;
    };
    platform_stats?: Record<string, unknown>;
  };
}

export interface MultiAgentAnalyzeResponse {
  success: boolean;
  data?: {
    overall_credibility?: number;
    credibility_level?: string;
    risk_flags?: string[];
    consensus_points?: string[];
    conflicts?: string[];
    processing_time_ms?: number;
  };
}

export const verificationService = {
  async layer1OfficialAnalyze(content: string, sourcePlatform = 'manual') {
    return apiClient.post<EnhancedAnalyzeResponse>(
      `${API_CONFIG.endpoints.intelEnhanced.base}/analyze/enhanced`,
      {
        content,
        source_platform: sourcePlatform,
      }
    );
  },

  async layer2MediaSearch(keyword: string, platforms?: string[]) {
    const resolvedPlatforms = platforms && platforms.length > 0 ? platforms : ['weibo', 'xinhua', 'news'];
    return apiClient.post<MultiPlatformSearchResponse>(
      `${API_CONFIG.endpoints.multiplatform.base}/search`,
      {
        keyword,
        platforms: resolvedPlatforms,
        limit_per_platform: 10,
      }
    );
  },

  async layer3CredibilityAnalyze(keyword: string, platforms?: string[]) {
    const resolvedPlatforms = platforms && platforms.length > 0 ? platforms : ['weibo', 'xinhua', 'news'];
    return apiClient.post<CredibilityReportResponse>(
      `${API_CONFIG.endpoints.multiplatform.base}/analyze-credibility`,
      {
        keyword,
        platforms: resolvedPlatforms,
        limit_per_platform: 30,
      }
    );
  },

  async layer4MultiAgentAnalyze(keyword: string, platforms?: string[]) {
    const resolvedPlatforms = platforms && platforms.length > 0 ? platforms : ['weibo', 'xinhua', 'news'];
    return apiClient.post<MultiAgentAnalyzeResponse>(
      `${API_CONFIG.endpoints.multiplatform.base}/multi-agent-analyze`,
      {
        keyword,
        platforms: resolvedPlatforms,
        limit_per_platform: 10,
      }
    );
  },
};

export default verificationService;
