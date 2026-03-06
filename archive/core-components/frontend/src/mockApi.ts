// Mock API - 用于演示GPT-5.3模型案例
import type { AnalyzeResponse, ToolMode } from './api'

// GPT-5.3 演示案例
export const GPT53_DEMO_CASE = {
  content: "OpenAI 宣布 GPT-5.3 模型正式发布，具备自我学习和代码重构能力，可以自动修复bug并优化算法性能",
  source_platform: "tech_news",
  metadata: {
    topic: "AI技术突破",
    viral_score: 0.95,
    claim_type: "product_release"
  }
}

// 模拟8步推理链
export function generateMockAnalysis(mode: ToolMode): AnalyzeResponse {
  const baseSteps = [
    {
      stage: "preprocessing",
      timestamp: new Date().toISOString(),
      reasoning: "提取核心主张：GPT-5.3发布、自我学习能力、自动修复bug",
      conclusion: "识别3个关键主张点，涉及技术突破声明",
      confidence: 0.92,
      evidence: ["原文提取", "关键词识别"],
      concerns: [],
      score_impact: 0.0
    },
    {
      stage: "physical_check",
      timestamp: new Date().toISOString(),
      reasoning: "检查时间一致性：GPT-5.3发布时间、技术实现时间线",
      conclusion: "OpenAI官方未发布GPT-5.3，最新为GPT-4系列",
      confidence: 0.98,
      evidence: ["OpenAI官网", "官方博客", "API文档"],
      concerns: ["版本号异常", "无官方确认"],
      score_impact: -0.25
    },
    {
      stage: "logical_check",
      timestamp: new Date().toISOString(),
      reasoning: "分析技术声称：自我学习能力、自动代码重构",
      conclusion: "声称的技术能力超出当前AI发展水平，存在夸大",
      confidence: 0.85,
      evidence: ["AI发展现状", "技术文献"],
      concerns: ["技术夸大", "缺乏证据"],
      score_impact: -0.20
    },
    {
      stage: "source_analysis",
      timestamp: new Date().toISOString(),
      reasoning: "分析信源可信度：发布账号历史、传播路径",
      conclusion: "信源为新注册账号，无历史发布记录，高度可疑",
      confidence: 0.88,
      evidence: ["账号画像", "注册时间", "历史内容"],
      concerns: ["新账号", "无信誉", "单源传播"],
      score_impact: -0.15
    }
  ]

  // 根据模式添加额外步骤
  let steps = [...baseSteps]
  
  if (mode === 'dual' || mode === 'search') {
    steps.push({
      stage: "cross_validation",
      timestamp: new Date().toISOString(),
      reasoning: "跨平台验证：Twitter、Reddit、技术论坛搜索",
      conclusion: "仅在低可信度论坛发现相似内容，主流媒体无报道",
      confidence: 0.90,
      evidence: ["Twitter搜索", "Reddit讨论", "HackerNews"],
      concerns: ["无主流媒体确认", "论坛讨论可疑"],
      score_impact: -0.10
    })
  }

  if (mode === 'enhanced') {
    steps.push(
      {
        stage: "cross_validation",
        timestamp: new Date().toISOString(),
        reasoning: "深度交叉验证：联系OpenAI员工、检查内部泄露",
        conclusion: "内部人士否认GPT-5.3存在，确认为虚假信息",
        confidence: 0.95,
        evidence: ["内部消息", "员工确认", "开发路线图"],
        concerns: ["完全伪造", "故意误导"],
        score_impact: -0.15
      },
      {
        stage: "anomaly_detection",
        timestamp: new Date().toISOString(),
        reasoning: "检测传播异常：水军账号、协同传播模式",
        conclusion: "发现23个新账号同步转发，疑似水军操作",
        confidence: 0.87,
        evidence: ["账号聚类", "传播图谱", "时间序列分析"],
        concerns: ["水军操作", "协同攻击", "故意散播"],
        score_impact: -0.10
      }
    )
  }

  // 计算最终分数
  const finalScore = Math.max(0, 0.5 + steps.reduce((sum, s) => sum + s.score_impact, 0))
  
  let finalLevel = "HIGH"
  if (finalScore < 0.2) finalLevel = "VERY_LOW"
  else if (finalScore < 0.4) finalLevel = "LOW"
  else if (finalScore < 0.6) finalLevel = "MEDIUM"
  else if (finalScore < 0.8) finalLevel = "HIGH"

  const riskFlags = steps.flatMap(s => s.concerns).filter((v, i, a) => a.indexOf(v) === i).slice(0, 3)

  return {
    intel: {
      id: `demo_${Date.now()}`,
      content_text: GPT53_DEMO_CASE.content,
      source_platform: GPT53_DEMO_CASE.source_platform,
      credibility_score: finalScore,
      credibility_level: finalLevel,
      created_at: new Date().toISOString(),
    },
    reasoning_chain: {
      steps,
      final_score: finalScore,
      final_level: finalLevel,
      risk_flags: riskFlags.length > 0 ? riskFlags : ["NEEDS_REVIEW"],
      total_confidence: steps.reduce((sum, s) => sum + s.confidence, 0) / steps.length,
      processing_time_ms: Math.floor(Math.random() * 3000) + 2000
    },
    processing_time_ms: Math.floor(Math.random() * 3000) + 2000
  }
}

// Mock API调用
export async function mockAnalyze(mode: ToolMode): Promise<AnalyzeResponse> {
  // 模拟网络延迟
  await new Promise(resolve => setTimeout(resolve, 2000))
  return generateMockAnalysis(mode)
}

// Mock 搜索结果
export async function mockSearch(): Promise<any> {
  await new Promise(resolve => setTimeout(resolve, 1500))
  return {
    success: true,
    keyword: "GPT-5.3",
    data: {
      twitter: [
        { id: "1", content: "GPT-5.3是假的，大家别信", author: "@tech_expert", timestamp: "2024-01-15T10:00:00Z" },
        { id: "2", content: "OpenAI官方没有发布GPT-5.3", author: "@ai_researcher", timestamp: "2024-01-15T09:30:00Z" }
      ],
      reddit: [
        { id: "3", content: "This is fake news, GPT-5.3 doesn't exist", author: "u/skeptic", timestamp: "2024-01-15T08:00:00Z" }
      ]
    },
    total_posts: 156,
    platform_count: 3
  }
}
