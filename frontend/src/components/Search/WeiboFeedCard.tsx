import type { NormalizedSearchPost } from '../../types/runtime'
import { Badge, Card } from '../common'

interface WeiboFeedCardProps {
  post: NormalizedSearchPost
}

function formatTime(timestamp?: string): string {
  if (!timestamp) return '未知时间'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return date.toLocaleString('zh-CN')
}

function credibilityVariant(score?: number): 'default' | 'success' | 'warning' | 'danger' {
  if (typeof score !== 'number') return 'default'
  if (score >= 0.7) return 'success'
  if (score >= 0.45) return 'warning'
  return 'danger'
}

export function WeiboFeedCard({ post }: WeiboFeedCardProps) {
  return (
    <Card className="border-slate-700/80 bg-slate-950/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">{post.platform}</p>
          <h4 className="mt-1 text-base font-bold leading-6 text-slate-100">{post.title}</h4>
          <p className="mt-1 text-xs text-slate-500">{post.author} · {formatTime(post.timestamp)}</p>
        </div>
        <Badge variant={credibilityVariant(post.credibilityScore)}>
          {typeof post.credibilityScore === 'number'
            ? `可信度 ${Math.round(post.credibilityScore * 100)}%`
            : '暂无平台评分'}
        </Badge>
      </div>

      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
        {post.content || '后端返回记录暂无正文内容。'}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span className="rounded-full border border-slate-700 px-2 py-1">
          👍 {post.engagement.likes}
        </span>
        <span className="rounded-full border border-slate-700 px-2 py-1">
          💬 {post.engagement.comments}
        </span>
        <span className="rounded-full border border-slate-700 px-2 py-1">
          🔁 {post.engagement.shares}
        </span>
        {post.url && (
          <a
            href={post.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-cyan-200 hover:bg-cyan-500/20"
          >
            查看原文
          </a>
        )}
      </div>
    </Card>
  )
}
