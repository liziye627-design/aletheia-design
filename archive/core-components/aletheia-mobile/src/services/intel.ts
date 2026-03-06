/**
 * Intel Service - Intelligence Analysis API calls
 */

import apiClient from './api';
import { API_CONFIG } from './config';
import type {
  IntelAnalyzeRequest,
  IntelAnalyzeResponse,
  IntelResult,
  TrendingTopicsResponse,
} from '../types';

interface SearchParams {
  keyword?: string;
  platform?: string;
  credibility_min?: number;
  credibility_max?: number;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

interface SearchResponse {
  items: IntelResult[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export const intelService = {
  /**
   * Analyze a piece of content for credibility
   */
  async analyze(request: IntelAnalyzeRequest): Promise<IntelAnalyzeResponse> {
    return apiClient.post<IntelAnalyzeResponse>(
      API_CONFIG.endpoints.intel.analyze,
      request
    );
  },

  /**
   * Batch analyze multiple items
   */
  async batchAnalyze(items: IntelAnalyzeRequest[]): Promise<IntelAnalyzeResponse[]> {
    return apiClient.post<IntelAnalyzeResponse[]>(
      API_CONFIG.endpoints.intel.batch,
      { items }
    );
  },

  /**
   * Search historical analysis records
   */
  async search(params: SearchParams): Promise<SearchResponse> {
    return apiClient.post<SearchResponse>(
      API_CONFIG.endpoints.intel.search,
      params
    );
  },

  /**
   * Get trending topics
   */
  async getTrending(): Promise<TrendingTopicsResponse> {
    return apiClient.get<TrendingTopicsResponse>(
      API_CONFIG.endpoints.intel.trending
    );
  },

  /**
   * Get intel detail by ID
   */
  async getById(id: string): Promise<IntelAnalyzeResponse> {
    return apiClient.get<IntelAnalyzeResponse>(
      API_CONFIG.endpoints.intel.detail(id)
    );
  },

  /**
   * Delete an intel record
   */
  async delete(id: string): Promise<void> {
    return apiClient.delete(API_CONFIG.endpoints.intel.detail(id));
  },
};

export default intelService;
