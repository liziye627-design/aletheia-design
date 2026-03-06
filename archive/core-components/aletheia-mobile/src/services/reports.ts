/**
 * Reports Service - Report generation API calls
 */

import apiClient from './api';
import { API_CONFIG } from './config';
import type { Report, ReportListResponse } from '../types';

interface GenerateReportRequest {
  title: string;
  content: string;
  template_id?: string;
}

interface ReportParams {
  page?: number;
  page_size?: number;
  tags?: string[];
}

export const reportsService = {
  /**
   * Get reports list
   */
  async getReports(params: ReportParams = {}): Promise<ReportListResponse> {
    const { page = 1, page_size = 20, tags } = params;
    
    return apiClient.get<ReportListResponse>(
      API_CONFIG.endpoints.reports.list,
      { page, page_size, tags }
    );
  },

  /**
   * Get report detail by ID
   */
  async getById(id: string): Promise<Report> {
    return apiClient.get<Report>(
      API_CONFIG.endpoints.reports.detail(id)
    );
  },

  /**
   * Generate a new report
   */
  async generate(request: GenerateReportRequest): Promise<Report> {
    return apiClient.post<Report>(
      API_CONFIG.endpoints.reports.generate,
      request
    );
  },

  /**
   * Get mock reports for development
   */
  getMockReports(): Report[] {
    return [
      {
        id: '1',
        title: 'AI领域虚假信息分析报告 - 2026年Q1',
        summary: '本季度AI领域共检测到1,247条疑似虚假信息，主要集中在技术突破夸大宣传和市场预测误导...',
        content_html: '<h1>报告内容</h1><p>详细分析...</p>',
        credibility_score: 0.89,
        created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
        updated_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
        sources: [],
        tags: ['AI', '季度报告', '技术'],
      },
      {
        id: '2',
        title: '社交媒体健康谣言专项分析',
        summary: '针对近期社交媒体上流传的健康类谣言进行深度分析，涉及超过500条信息...',
        content_html: '<h1>报告内容</h1><p>详细分析...</p>',
        credibility_score: 0.92,
        created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        updated_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        sources: [],
        tags: ['健康', '社交媒体', '谣言'],
      },
    ];
  },
};

export default reportsService;
