import { API_CONFIG } from '../services/config';
import type {
  CrossPlatformCredibilityResponse,
  EnhancedAnalyzeResponse,
  MultiPlatformSearchResponse,
} from './types';

const API_ROOT = `${API_CONFIG.baseURL}${API_CONFIG.apiVersion}`;

function toPlatforms(sourcePlatform?: string) {
  if (!sourcePlatform || sourcePlatform === 'mixed') {
    return undefined;
  }

  return [sourcePlatform];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(init?.headers || {}),
    },
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = (payload as { detail?: string }).detail;
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return payload as T;
}

export async function analyzeEnhanced(content: string, sourcePlatform: string) {
  return request<EnhancedAnalyzeResponse>('/intel/enhanced/analyze/enhanced', {
    method: 'POST',
    body: JSON.stringify({
      content,
      source_platform: sourcePlatform,
    }),
  });
}

export async function searchAcrossPlatforms(keyword: string, sourcePlatform?: string) {
  return request<MultiPlatformSearchResponse>('/multiplatform/search', {
    method: 'POST',
    body: JSON.stringify({
      keyword,
      platforms: toPlatforms(sourcePlatform),
      limit_per_platform: 10,
    }),
  });
}

export async function buildCredibilityReport(keyword: string, sourcePlatform?: string) {
  return request<CrossPlatformCredibilityResponse>(
    '/multiplatform/analyze-credibility',
    {
      method: 'POST',
      body: JSON.stringify({
        keyword,
        platforms: toPlatforms(sourcePlatform),
        limit_per_platform: 30,
      }),
    }
  );
}
