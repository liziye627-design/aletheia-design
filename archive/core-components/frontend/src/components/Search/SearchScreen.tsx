import { useMemo } from 'react'
import type { VerificationRunState, NormalizedSearchPost } from '../../types/runtime'
import { Card, EmptyState } from '../common'
import { WeiboFeedCard } from './WeiboFeedCard'

interface SearchScreenProps {
  run: VerificationRunState | null
  isRunning: boolean
}

// 空结果原因码的通俗化表达
const NO_DATA_REASON_MAP: Record<string, { label: string; icon: string; color: string; action: string }> = {
  FALLBACK_EMPTY: {
    label: '所有平台均未返回结果',
    icon: '📭',
    color: 'amber',
    action: '建议调整关键词或尝试更具体的表述',
  },
  NETWORK_UNREACHABLE: {
    label: '网络连接失败',
    icon: '🌐',
    color: 'red',
    action: '请检查网络环境或稍后重试',
  },
  MEDIACRAWLER_LOGIN_REQUIRED: {
    label: '需要登录才能访问',
    icon: '🔐',
    color: 'orange',
    action: '该平台需要登录态，请联系管理员配置 Cookies',
  },
  INSUFFICIENT_EVIDENCE: {
    label: '证据不足',
    icon: '📊',
    color: 'amber',
    action: '建议补充更多关键词进行检索',
  },
  TIMEOUT: {
    label: '检索超时',
    icon: '⏱️',
    color: 'amber',
    action: '平台响应较慢，建议稍后重试',
  },
  MISSING_TOKEN: {
    label: '缺少认证凭据',
    icon: '🔑',
    color: 'orange',
    action: '该平台需要 API Token，请联系管理员配置',
  },
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function pickText(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return ''
}

function normalizePosts(run: VerificationRunState | null): NormalizedSearchPost[] {
  if (!run?.search?.data) return []

  return Object.entries(run.search.data)
    .flatMap(([platform, posts]) => {
      if (!Array.isArray(posts)) return []
      const platformScore =
        run.multiAgent?.platform_results?.[platform]?.small_model_analysis?.credibility_score

      return posts.map((raw, index) => {
        const item = (raw || {}) as Record<string, unknown>
        const title = pickText(item, ['title', 'headline', 'name']) || '未命名内容'
        const content = pickText(item, ['content', 'text', 'summary', 'desc', 'body'])
        const author = pickText(item, ['author', 'username', 'screen_name']) || '未知来源'
        const url = pickText(item, ['url', 'link', 'original_url']) || undefined
        const timestamp = pickText(item, ['timestamp', 'created_at', 'publish_time']) || undefined

        return {
          id: asString(item.id) || `${platform}-${index}`,
          platform,
          title,
          content,
          author,
          url,
          timestamp,
          engagement: {
            likes: asNumber(item.like_count ?? item.likes),
            comments: asNumber(item.comment_count ?? item.comments),
            shares: asNumber(item.share_count ?? item.shares),
          },
          credibilityScore: typeof platformScore === 'number' ? platformScore : undefined,
        }
      })
    })
    .sort((a, b) => {
      const left = a.timestamp ? new Date(a.timestamp).getTime() : 0
      const right = b.timestamp ? new Date(b.timestamp).getTime() : 0
      return right - left
    })
}

function shortText(value: string, max = 360): string {
  if (!value) return ''
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length <= max) return compact
  return `${compact.slice(0, max)}...`
}

function fieldToDisplay(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value
      .slice(0, 5)
      .map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
      .join(' | ')
  }
  if (value && typeof value === 'object') return JSON.stringify(value)
  return ''
}

export function SearchScreen({ run, isRunning }: SearchScreenProps) {
  const posts = useMemo(() => normalizePosts(run), [run])
  const summary = run?.aggregate?.summary
  const anomalies = run?.credibility?.anomalies ?? []
  const rendered = run?.renderedExtract
  const platformErrors = run?.multiAgent?.platform_errors ?? run?.multiAgent?.no_data_explainer?.platform_errors ?? {}
  const noDataExplainer = run?.multiAgent?.no_data_explainer

  // 判断是否需要显示空结果解释
  const showNoDataExplainer = noDataExplainer && (run?.search?.total_posts ?? 0) === 0 && !isRunning

  if (!run) {
    return <EmptyState message="暂无检索任务，请先在核验页提交内容。" />
  }

  return (
    <div className="space-y-5">
      {/* 为什么没查到面板 - 核心改进 */}
      {showNoDataExplainer && (
        <Card className="border-amber-500/40 bg-amber-500/10">
          <h3 className="text-sm font-bold uppercase tracking-wide text-amber-200 mb-4">
            ⚠️ 为什么没有查到结果？
          </h3>

          {/* 主要原因 */}
          <div className="rounded-lg border border-amber-400/40 bg-amber-900/30 p-4 mb-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">
                {NO_DATA_REASON_MAP[noDataExplainer?.reason_code ?? '']?.icon ?? '❓'}
              </span>
              <div>
                <p className="font-medium text-amber-100">
                  {noDataExplainer?.reason_text ??
                    NO_DATA_REASON_MAP[noDataExplainer?.reason_code ?? '']?.label ??
                    '未知原因'}
                </p>
                <p className="mt-1 text-sm text-amber-200/70">
                  {NO_DATA_REASON_MAP[noDataExplainer?.reason_code ?? '']?.action ?? '请稍后重试'}
                </p>
              </div>
            </div>
          </div>

          {/* 统计数据 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 p-3">
              <p className="text-xs text-amber-400">尝试平台</p>
              <p className="mt-1 text-lg font-bold text-amber-100">
                {noDataExplainer?.attempted_platforms?.length ?? 0}
              </p>
            </div>
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 p-3">
              <p className="text-xs text-amber-400">命中条目</p>
              <p className="mt-1 text-lg font-bold text-amber-100">
                {noDataExplainer?.hit_count ?? 0}
              </p>
            </div>
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 p-3">
              <p className="text-xs text-amber-400">可回溯条目</p>
              <p className="mt-1 text-lg font-bold text-amber-100">
                {noDataExplainer?.retrievable_count ?? 0}
              </p>
            </div>
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 p-3">
              <p className="text-xs text-amber-400">覆盖率</p>
              <p className="mt-1 text-lg font-bold text-amber-100">
                {Math.round((noDataExplainer?.coverage_ratio ?? 0) * 100)}%
              </p>
            </div>
          </div>

          {/* 失败平台原因 */}
          {noDataExplainer?.platform_errors &&
            Object.keys(noDataExplainer.platform_errors).length > 0 && (
              <div className="mb-4">
                <p className="text-xs font-medium text-amber-300 mb-2">各平台失败原因：</p>
                <div className="space-y-1">
                  {Object.entries(noDataExplainer.platform_errors).map(
                    ([platform, error]) => (
                      <div
                        key={platform}
                        className="text-xs text-amber-200/80 flex items-center gap-2"
                      >
                        <span className="font-medium text-amber-100">{platform}</span>
                        <span className="text-amber-400">→</span>
                        <span>{Array.isArray(error) ? error.join(', ') : String(error)}</span>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

          {/* 建议补检关键词 */}
          {(noDataExplainer?.suggested_queries ?? noDataExplainer?.next_queries)?.length ? (
            <div>
              <p className="text-xs font-medium text-amber-300 mb-2">
                💡 建议尝试以下关键词：
              </p>
              <div className="flex flex-wrap gap-2">
                {(noDataExplainer?.suggested_queries ?? noDataExplainer?.next_queries ?? [])
                  .slice(0, 6)
                  .map((query, idx) => (
                    <span
                      key={idx}
                      className="rounded-full border border-amber-400/40 bg-amber-500/20 px-3 py-1 text-sm text-amber-100 cursor-pointer hover:bg-amber-500/30 transition"
                      onClick={() => {
                        // 可扩展：点击后自动填入搜索框
                        navigator.clipboard?.writeText(query)
                      }}
                      title="点击复制"
                    >
                      {query}
                    </span>
                  ))}
              </div>
            </div>
          ) : null}
        </Card>
      )}

      <Card className="border-slate-700/80 bg-slate-900/70">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-500">关键词</p>
            <p className="mt-1 text-lg font-bold text-slate-100">{run.keyword}</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-500">搜索命中</p>
            <p className="mt-1 text-lg font-bold text-slate-100">{run.search?.total_posts ?? 0}</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-500">覆盖平台</p>
            <p className="mt-1 text-lg font-bold text-slate-100">{run.search?.platform_count ?? 0}</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-500">异常项</p>
            <p className="mt-1 text-lg font-bold text-slate-100">{anomalies.length}</p>
          </div>
        </div>
      </Card>

      {(run.sourceUrl || rendered) && (
        <Card className="border-cyan-500/30 bg-cyan-500/5">
          <h3 className="text-sm font-bold uppercase tracking-wide text-cyan-200">网页渲染抽取结果</h3>
          <p className="mt-1 text-xs text-cyan-100/80">
            来源 URL：{run.sourceUrl || rendered?.url || '未提供'}
          </p>
          {!rendered && (
            <p className="mt-3 rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-400">
              {isRunning ? 'Playwright 渲染抽取进行中...' : '本次任务未返回渲染抽取结果。'}
            </p>
          )}
          {rendered && (
            <div className="mt-3 space-y-3">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                  <p className="text-xs text-slate-500">DOM稳定</p>
                  <p className="mt-1 font-semibold text-slate-100">
                    {rendered.diagnostics.dom_stable ? '是' : '否'}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                  <p className="text-xs text-slate-500">networkidle</p>
                  <p className="mt-1 font-semibold text-slate-100">
                    {rendered.diagnostics.playwright_networkidle_reached ? '达成' : '未达成'}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                  <p className="text-xs text-slate-500">接口JSON</p>
                  <p className="mt-1 font-semibold text-slate-100">{rendered.api_responses.length}</p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                  <p className="text-xs text-slate-500">滚动次数</p>
                  <p className="mt-1 font-semibold text-slate-100">{rendered.diagnostics.scroll_count}</p>
                </div>
              </div>

              <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">字段抽取</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {Object.entries(rendered.fields || {}).map(([field, value]) => (
                    <div key={field} className="rounded-lg border border-slate-700/80 bg-slate-900/70 px-2.5 py-2">
                      <p className="text-xs font-semibold text-cyan-300">{field}</p>
                      <p className="mt-1 text-xs leading-5 text-slate-200">{fieldToDisplay(value) || '（空）'}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">可见文本预览</p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                  {shortText(rendered.visible_text, 800) || '（空）'}
                </p>
              </div>
            </div>
          )}
        </Card>
      )}

      {summary && (
        <Card className="border-slate-700/80 bg-slate-900/70">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300">聚合统计</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {Object.entries(run.aggregate?.platform_stats ?? {}).map(([platform, stat]) => (
              <div key={platform} className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                <p className="font-semibold text-slate-200">{platform}</p>
                <p className="mt-1 text-xs text-slate-500">post_count</p>
                <p className="text-slate-100">{stat.post_count}</p>
                <p className="mt-1 text-xs text-slate-500">avg_engagement</p>
                <p className="text-slate-100">{Number(stat.avg_engagement ?? 0).toFixed(2)}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="border-slate-700/80 bg-slate-900/70">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-300">信息流视图</h3>
        <p className="mt-1 text-xs text-slate-500">
          这里展示后端 `multiplatform/search` 实时返回的信源条目，已按时间排序。
        </p>
        <div className="mt-4 space-y-3">
          {posts.length === 0 && !showNoDataExplainer && (
            <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-4 py-4">
              {isRunning ? (
                <div className="flex items-center gap-3">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-cyan-400"></div>
                  <div>
                    <p className="text-sm text-slate-300">后端正在检索中...</p>
                    <p className="text-xs text-slate-500 mt-1">结果会陆续出现，请稍候</p>
                  </div>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-amber-300">⚠️ 当前任务没有返回可展示的检索结果</p>
                  <p className="text-xs text-slate-400 mt-2">
                    可能的原因：关键词过于具体、平台无相关内容、或网络问题。
                    建议尝试调整关键词后重新检索。
                  </p>
                </div>
              )}
            </div>
          )}
          {posts.slice(0, 40).map((post) => (
            <WeiboFeedCard key={`${post.platform}-${post.id}`} post={post} />
          ))}
        </div>
      </Card>

      {anomalies.length > 0 && (
        <Card className="border-amber-500/40 bg-amber-500/10">
          <h3 className="text-sm font-bold uppercase tracking-wide text-amber-200">异常告警流</h3>
          <div className="mt-3 space-y-2">
            {anomalies.map((item, index) => (
              <div key={`${item.type}-${index}`} className="rounded-lg border border-amber-400/40 bg-amber-900/30 px-3 py-2 text-sm text-amber-100">
                <p className="font-semibold">
                  {item.type} · {item.platform}
                </p>
                <p className="mt-1 text-xs leading-5">{item.description}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {Object.keys(platformErrors).length > 0 && (
        <Card className="border-red-500/40 bg-red-500/10">
          <h3 className="text-sm font-bold uppercase tracking-wide text-red-200">平台检索错误</h3>
          <p className="mt-1 text-xs text-red-100/70">
            以下平台在检索过程中遇到问题，可能导致数据不完整：
          </p>
          <div className="mt-3 space-y-2">
            {Object.entries(platformErrors).map(([platform, errors]) => {
              const errorList = Array.isArray(errors) ? errors : [String(errors)]
              return (
                <div key={platform} className="rounded-lg border border-red-400/40 bg-red-900/30 px-3 py-2 text-sm text-red-100">
                  <p className="font-semibold text-red-200">{platform}</p>
                  <div className="mt-1 space-y-1">
                    {errorList.map((err, idx) => (
                      <p key={idx} className="text-xs leading-5 text-red-100/80">• {err}</p>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
