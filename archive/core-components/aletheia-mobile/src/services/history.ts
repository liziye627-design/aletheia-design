/**
 * History Service
 * 生成文章历史：后端优先，失败回落本地持久化
 */

import * as SecureStore from 'expo-secure-store';

import { reportsService } from './reports';
import type { GeneratedArticleRecord, Report } from '../types';

const HISTORY_KEY = 'aletheia_generated_articles';

type SaveArticleInput = {
  title: string;
  topic: string;
  kind: 'refute' | 'approve';
  credibility: number;
  content: string;
  sources?: string[];
};

function mapReportToRecord(report: Report): GeneratedArticleRecord {
  return {
    id: report.id,
    title: report.title,
    topic: report.tags?.[0] || '未分类主题',
    kind: report.title.includes('辟谣') ? 'refute' : 'approve',
    credibility: report.credibility_score,
    content: report.content_html || report.summary || '',
    createdAt: report.created_at,
    sources: (report.sources || []).map((item) => item.url).filter(Boolean),
  };
}

async function readLocalHistory(): Promise<GeneratedArticleRecord[]> {
  const raw = await SecureStore.getItemAsync(HISTORY_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as GeneratedArticleRecord[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeLocalHistory(items: GeneratedArticleRecord[]) {
  await SecureStore.setItemAsync(HISTORY_KEY, JSON.stringify(items));
}

export const historyService = {
  async getHistoryArticles(): Promise<GeneratedArticleRecord[]> {
    try {
      const response = await reportsService.getReports({ page: 1, page_size: 50 });
      if (Array.isArray(response?.items)) {
        const backendItems = response.items.map(mapReportToRecord);
        if (backendItems.length > 0) {
          await writeLocalHistory(backendItems);
          return backendItems;
        }
      }
    } catch {
      // ignore backend error and fallback to local
    }

    return readLocalHistory();
  },

  async saveGeneratedArticle(input: SaveArticleInput): Promise<GeneratedArticleRecord> {
    let saved: GeneratedArticleRecord | null = null;

    try {
      const report = await reportsService.generate({
        title: input.title,
        content: input.content,
      });

      if ((report as Report)?.id) {
        saved = {
          ...mapReportToRecord(report as Report),
          topic: input.topic,
          kind: input.kind,
          credibility: input.credibility,
          sources: input.sources,
        };
      }
    } catch {
      // ignore backend error and fallback to local
    }

    if (!saved) {
      saved = {
        id: `local-${Date.now()}`,
        title: input.title,
        topic: input.topic,
        kind: input.kind,
        credibility: input.credibility,
        content: input.content,
        createdAt: new Date().toISOString(),
        sources: input.sources,
      };
    }

    const current = await readLocalHistory();
    const next = [saved, ...current].slice(0, 200);
    await writeLocalHistory(next);
    return saved;
  },
};

export default historyService;
