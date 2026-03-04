/**
 * Document Export Service
 * 统一文档导出结构：TXT/Markdown/HTML/JSON + PDF/DOCX（后端扩展位）
 */

import apiClient from './api';
import type { DocumentArtifact, DocumentFormat } from '../types';

type ExportInput = {
  title: string;
  topic: string;
  verdict: '辟谣' | '认可';
  credibility: number;
  content: string;
  sources?: string[];
};

function safeName(value: string) {
  return value.replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 80);
}

function toMarkdown(input: ExportInput) {
  return [
    `# ${input.title}`,
    '',
    `- 话题：${input.topic}`,
    `- 结论：${input.verdict}`,
    `- 可信度：${Math.round(input.credibility * 100)}%`,
    ...(input.sources?.length ? ['- 信源：', ...input.sources.map((s) => `  - ${s}`)] : []),
    '',
    '---',
    '',
    input.content,
  ].join('\n');
}

function toPlainText(input: ExportInput) {
  return [
    input.title,
    `话题: ${input.topic}`,
    `结论: ${input.verdict}`,
    `可信度: ${Math.round(input.credibility * 100)}%`,
    ...(input.sources?.length ? [`信源: ${input.sources.join(' | ')}`] : []),
    '',
    input.content,
  ].join('\n');
}

function toHtml(input: ExportInput) {
  const escaped = input.content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>');

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${input.title}</title>
  <style>
    body { font-family: -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif; margin: 24px; color: #111; }
    h1 { margin-bottom: 8px; }
    .meta { color: #444; font-size: 14px; margin-bottom: 16px; }
    .block { line-height: 1.7; white-space: normal; }
  </style>
</head>
<body>
  <h1>${input.title}</h1>
  <div class="meta">话题：${input.topic} | 结论：${input.verdict} | 可信度：${Math.round(
    input.credibility * 100
  )}%</div>
  <div class="block">${escaped}</div>
</body>
</html>`;
}

function toJson(input: ExportInput) {
  return JSON.stringify(
    {
      title: input.title,
      topic: input.topic,
      verdict: input.verdict,
      credibility: input.credibility,
      sources: input.sources || [],
      content: input.content,
      generated_at: new Date().toISOString(),
    },
    null,
    2
  );
}

export const documentExportService = {
  getFormatMatrix() {
    return [
      { format: 'txt' as const, available: true, mode: 'native', note: '纯文本，通用性最高' },
      { format: 'md' as const, available: true, mode: 'native', note: '适合公众号与知识库二次编辑' },
      { format: 'html' as const, available: true, mode: 'native', note: '可直接浏览器预览和打印' },
      { format: 'json' as const, available: true, mode: 'native', note: '结构化存档/系统对接' },
      { format: 'pdf' as const, available: true, mode: 'backend', note: '后端导出接口（当前为基础实现）' },
      { format: 'docx' as const, available: true, mode: 'backend', note: '后端导出接口（当前为基础实现）' },
    ];
  },

  buildNativeArtifacts(input: ExportInput): DocumentArtifact[] {
    const base = `${safeName(input.topic || input.title)}_${Date.now()}`;
    return [
      {
        format: 'txt',
        fileName: `${base}.txt`,
        mimeType: 'text/plain; charset=utf-8',
        content: toPlainText(input),
      },
      {
        format: 'md',
        fileName: `${base}.md`,
        mimeType: 'text/markdown; charset=utf-8',
        content: toMarkdown(input),
      },
      {
        format: 'html',
        fileName: `${base}.html`,
        mimeType: 'text/html; charset=utf-8',
        content: toHtml(input),
      },
      {
        format: 'json',
        fileName: `${base}.json`,
        mimeType: 'application/json; charset=utf-8',
        content: toJson(input),
      },
    ];
  },

  async exportByBackend(format: Extract<DocumentFormat, 'pdf' | 'docx'>, input: ExportInput) {
    // 预留：后端导出接口（当前后端未实现）
    return apiClient.post<{ file_name: string; mime_type: string; content_base64: string }>(
      '/reports/export',
      {
        format,
        payload: input,
      }
    );
  },
};

export default documentExportService;
