/**
 * Feeds Service - Real-time feeds API calls
 */

import apiClient from './api';
import { API_CONFIG } from './config';
import type { FeedItem, FeedResponse } from '../types';

interface FeedFilter {
  platforms?: string[];
  credibility_min?: number;
  credibility_max?: number;
  tags?: string[];
  date_from?: string;
  date_to?: string;
}

interface FeedParams {
  page?: number;
  page_size?: number;
  filter?: FeedFilter;
}

export const feedsService = {
  /**
   * Get feeds list
   */
  async getFeeds(params: FeedParams = {}): Promise<FeedResponse> {
    const { page = 1, page_size = 20, filter } = params;
    
    return apiClient.get<FeedResponse>(
      API_CONFIG.endpoints.feeds.list,
      { page, page_size, ...filter }
    );
  },

  /**
   * Set feed filter preferences
   */
  async setFilter(filter: FeedFilter): Promise<{ success: boolean }> {
    return apiClient.post(API_CONFIG.endpoints.feeds.filter, filter);
  },

  /**
   * Get mock feeds for development
   */
  getMockFeeds(): FeedItem[] {
    return [
      {
        id: '1',
        title: 'New AI Regulation Framework Released',
        snippet: 'The global committee has finally agreed on the terms for AI safety regulations that will affect all major tech companies...',
        source: 'TechCrunch',
        source_platform: 'news',
        published_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
        credibility_score: 0.98,
        risk_tags: [],
        url: 'https://techcrunch.com/example',
      },
      {
        id: '2',
        title: 'Breaking: Major Financial Scandal Uncovered',
        snippet: 'Investigation reveals systematic fraud across multiple institutions spanning over a decade...',
        source: 'Reuters',
        source_platform: 'news',
        published_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
        credibility_score: 0.85,
        risk_tags: ['unverified_claims'],
        url: 'https://reuters.com/example',
      },
      {
        id: '3',
        title: 'Viral Social Media Post Claims Miracle Cure',
        snippet: 'A post claiming a simple household ingredient can cure common diseases has gone viral...',
        source: 'Weibo User',
        source_platform: 'weibo',
        published_at: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
        credibility_score: 0.12,
        risk_tags: ['misinformation', 'health_claim', 'viral'],
        url: 'https://weibo.com/example',
      },
      {
        id: '4',
        title: 'Climate Report: Record Temperatures Expected',
        snippet: 'Scientists warn of unprecedented heat waves in the coming summer months based on current data...',
        source: 'Nature',
        source_platform: 'academic',
        published_at: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
        credibility_score: 0.95,
        risk_tags: [],
        url: 'https://nature.com/example',
      },
      {
        id: '5',
        title: 'Politician Denies Corruption Allegations',
        snippet: 'Local official responds to leaked documents suggesting improper financial dealings...',
        source: 'Local News',
        source_platform: 'news',
        published_at: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
        credibility_score: 0.55,
        risk_tags: ['disputed', 'political'],
        url: 'https://localnews.com/example',
      },
    ];
  },
};

export default feedsService;
