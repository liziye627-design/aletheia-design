import { useMemo, useState } from 'react'
import type { ToolMode, ReportResponse } from '../../api'
import { Button, Card } from '../common'

const SUPPORTED_PLATFORMS = [
  'weibo',
  'xinhua',
  'news',
  'xiaohongshu',
  'zhihu',
  'bilibili',
  'douyin',
  'twitter',
]

export interface VerificationRunRequest {
  content: string
  keyword: string
  sourceUrl: string
  mode: ToolMode
  platforms: string[]
  imageUrls: string[]
}

interface VerificationFormProps {
  onSubmit: (payload: VerificationRunRequest) => void
  isLoading: boolean
  error: string | null
  recentReports: ReportResponse[]
}

function parseImageUrls(input: string): string[] {
  return input
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

export function VerificationForm({
  onSubmit,
  isLoading,
  error,
  recentReports,
}: VerificationFormProps) {
  const [content, setContent] = useState('')
  const [keyword, setKeyword] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [mode, setMode] = useState<ToolMode>('enhanced')
  const [platforms, setPlatforms] = useState<string[]>([
    'weibo',
    'xinhua',
    'xiaohongshu',
    'zhihu',
  ])
  const [imageUrlInput, setImageUrlInput] = useState('')

  const selectedPlatformLabel = useMemo(() => {
    if (platforms.length === 0) return '全部平台（后端默认）'
    return `${platforms.length} 个平台`
  }, [platforms.length])

  const canSubmit = content.trim().length > 0 && !isLoading

  const togglePlatform = (platform: string) => {
    setPlatforms((prev) => {
      if (prev.includes(platform)) {
        return prev.filter((item) => item !== platform)
      }
      return [...prev, platform]
    })
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return

    onSubmit({
      content: content.trim(),
      keyword: keyword.trim(),
      sourceUrl: sourceUrl.trim(),
      mode,
      platforms,
      imageUrls: parseImageUrls(imageUrlInput),
    })
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1.25fr_0.75fr]">
      <Card className="border-slate-700/80 bg-slate-900/70 backdrop-blur">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <h2 className="text-2xl font-black tracking-tight text-white">急救室核验入口</h2>
            <p className="text-sm text-slate-400">
              提交 claim 后会并行调用后端增强推理、多平台检索、跨平台可信度分析、多 Agent
              编排，并自动生成证据报告。
            </p>
          </div>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
              Claim 内容
            </span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="例如：网传某机构将在48小时内发布重大政策变动..."
              className="min-h-[170px] w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm leading-6 text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                搜索关键词（可选）
              </span>
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="留空将从 claim 自动提取"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                网页 URL（可选）
              </span>
              <input
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder="https://example.com/article"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
              />
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                核验模式
              </span>
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value as ToolMode)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                <option value="enhanced">增强推理（8步）</option>
                <option value="dual">双工模式（分析+检索）</option>
                <option value="search">检索优先（信源流）</option>
              </select>
            </label>
            <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-slate-400">
              提供 URL 时，会额外调用 Playwright 渲染抽取接口，返回页面可见文本、结构化字段和接口 JSON。
            </div>
          </div>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
              图像 URL（可选，逗号/换行分隔）
            </span>
            <textarea
              value={imageUrlInput}
              onChange={(event) => setImageUrlInput(event.target.value)}
              placeholder="https://example.com/1.png"
              className="min-h-[74px] w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
            />
          </label>

          <div className="rounded-2xl border border-slate-700/80 bg-slate-950/70 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                平台范围
              </span>
              <span className="text-xs text-cyan-300">{selectedPlatformLabel}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {SUPPORTED_PLATFORMS.map((platform) => {
                const active = platforms.includes(platform)
                return (
                  <button
                    key={platform}
                    type="button"
                    onClick={() => togglePlatform(platform)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                      active
                        ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200'
                        : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                    }`}
                  >
                    {platform}
                  </button>
                )
              })}
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <Button type="submit" size="lg" className="w-full bg-cyan-600 hover:bg-cyan-500" disabled={!canSubmit}>
            {isLoading ? '后端处理中，请稍候…' : '启动流式核验任务'}
          </Button>
        </form>
      </Card>

      <div className="space-y-4">
        <Card className="border-slate-700/80 bg-slate-900/65">
          <h3 className="text-sm font-bold text-slate-200">本次将调用的后端接口</h3>
          <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-400">
            <li>`POST /intel/enhanced/analyze/enhanced`</li>
            <li>`POST /multiplatform/search`</li>
            <li>`POST /multiplatform/aggregate`</li>
            <li>`POST /multiplatform/analyze-credibility`</li>
            <li>`POST /multiplatform/multi-agent-analyze`</li>
            <li>`POST /multiplatform/playwright-rendered-extract`（填写 URL 时）</li>
            <li>`POST /reports/generate`</li>
          </ul>
        </Card>

        <Card className="border-slate-700/80 bg-slate-900/65">
          <h3 className="text-sm font-bold text-slate-200">最近生成报告</h3>
          <div className="mt-3 space-y-2">
            {recentReports.length === 0 && (
              <p className="text-xs text-slate-500">暂无报告，提交任务后会自动生成。</p>
            )}
            {recentReports.slice(0, 6).map((report) => (
              <div
                key={report.id}
                className="rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="line-clamp-2 font-semibold text-slate-200">{report.title}</p>
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-cyan-300">
                    {Math.round(report.credibility_score * 100)}%
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">{new Date(report.created_at).toLocaleString('zh-CN')}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
