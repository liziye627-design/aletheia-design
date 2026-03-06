import { useEffect, useId, useMemo, useState } from 'react'
import mermaid from 'mermaid'

let mermaidReady = false

function ensureMermaid() {
  if (mermaidReady) return
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: {
      fontFamily: 'Noto Serif SC, Source Serif 4, serif',
      primaryColor: '#fbf6ee',
      primaryTextColor: '#2b241d',
      lineColor: '#bfae9b',
      secondaryColor: '#f4e7d5',
      tertiaryColor: '#f7f1e7',
    },
    flowchart: {
      curve: 'linear',
    },
  })
  mermaidReady = true
}

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

export function MermaidCard({
  title,
  subtitle,
  definition,
  className,
}: {
  title: string
  subtitle?: string
  definition: string
  className?: string
}) {
  const id = useId().replace(/[:]/g, '')
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')
  const renderedDefinition = useMemo(() => definition.trim(), [definition])

  useEffect(() => {
    let active = true
    ensureMermaid()

    const render = async () => {
      try {
        const { svg } = await mermaid.render(`mermaid-${id}`, renderedDefinition)
        if (active) {
          setSvg(svg)
          setError('')
        }
      } catch (err) {
        if (!active) return
        setSvg('')
        setError(err instanceof Error ? err.message : '渲染失败')
      }
    }

    if (renderedDefinition) {
      void render()
    }

    return () => {
      active = false
    }
  }, [id, renderedDefinition])

  return (
    <article className={cn('sub-card', 'mermaid-card', className)}>
      <div className="sub-head">
        <h4>{title}</h4>
        {subtitle && <span className="sub-meta">{subtitle}</span>}
      </div>
      {!renderedDefinition && <p className="empty-copy">暂无可视化数据。</p>}
      {renderedDefinition && !svg && !error && <p className="mermaid-loading">图表生成中...</p>}
      {error && (
        <div className="mermaid-error">
          <p>图表渲染失败：{error}</p>
          <pre>{renderedDefinition}</pre>
        </div>
      )}
      {svg && !error && (
        <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
      )}
    </article>
  )
}
