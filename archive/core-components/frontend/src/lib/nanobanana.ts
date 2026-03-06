export const NANOBANANA_URL = import.meta.env.VITE_NANOBANANA_URL || ''
export const JIMENG_URL = import.meta.env.VITE_JIMENG_URL || ''

export type NanoBananaTaskType = 'score_visual' | 'evidence_visual' | 'summary_cover'

export interface NanoBananaAgentTask {
  id: string
  type: NanoBananaTaskType
  title: string
  prompt: string
}

export interface NanoBananaAgentInput {
  headline: string
  summary: string
  scoreMermaid: string
  evidenceMermaid: string
  evidenceCount: number
  claimCount: number
  riskLevel: string
}

export function buildNanoBananaAgentPlan(input: NanoBananaAgentInput): NanoBananaAgentTask[] {
  const baseStyle = [
    '纸质报纸风信息图',
    '米色纸张纹理背景',
    '暖色墨线',
    '中文衬线标题',
    '留白清晰',
    '避免纯黑色',
  ].join('，')

  const scorePrompt = [
    `主题：${input.headline}`,
    `要点摘要：${input.summary}`,
    `请根据 Mermaid 饼图渲染一张“评分拆解”信息图：`,
    input.scoreMermaid,
    `风格要求：${baseStyle}。图上显示评分项与占比，保留简洁图例。`,
  ].join('\n')

  const evidencePrompt = [
    `主题：${input.headline}`,
    `证据数量：${input.evidenceCount} 条；主张数量：${input.claimCount} 条；风险等级：${input.riskLevel}`,
    `请根据 Mermaid 流程图渲染一张“证据链路图”信息图：`,
    input.evidenceMermaid,
    `风格要求：${baseStyle}。节点使用柔和边框，箭头清晰。`,
  ].join('\n')

  const summaryPrompt = [
    `主题：${input.headline}`,
    `摘要：${input.summary}`,
    `请生成一张“核查总结海报”，包含结论标题 + 核心数字（证据数、主张数、风险等级）。`,
    `风格要求：${baseStyle}。`,
  ].join('\n')

  return [
    {
      id: 'score_visual',
      type: 'score_visual',
      title: '评分拆解图',
      prompt: scorePrompt,
    },
    {
      id: 'evidence_visual',
      type: 'evidence_visual',
      title: '证据链路图',
      prompt: evidencePrompt,
    },
    {
      id: 'summary_cover',
      type: 'summary_cover',
      title: '总结报告封面',
      prompt: summaryPrompt,
    },
  ]
}
