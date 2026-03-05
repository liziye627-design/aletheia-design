import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

const streams = [
  { platform: 'X/Twitter', count: 122, state: '热度上升' },
  { platform: 'Reuters', count: 14, state: '稳定' },
  { platform: 'Fed', count: 6, state: '稳定' },
  { platform: 'Forum', count: 87, state: '异常扩散' },
]

const rows = [
  ['10:21:00', 'X', '@macro_watch 发布首发帖文', '高相关'],
  ['10:21:04', 'Forum', '同模板文案扩散至 23 个账号', '高风险'],
  ['10:21:07', 'Reuters', '发布事实核查更新', '权威'],
  ['10:21:08', 'Fed', '官方数据页被引用', '权威'],
  ['10:21:12', 'X', '二次转发速率下降 18%', '趋势变化'],
]

export default function SearchPage() {
  const [params] = useSearchParams()
  const mode = params.get('mode') ?? 'live'
  const modeTitle = useMemo(() => {
    if (mode === 'trending') return '热点跟踪模式'
    if (mode === 'aggregate') return '来源聚合模式'
    return '实时检索模式'
  }, [mode])

  return (
    <>
      <section className="head-row">
        <div>
          <h1>Search</h1>
          <p>多平台实时检索与流式更新 · {modeTitle}</p>
        </div>
      </section>

      <section className="panel">
        <div className="search-controls">
          <input value="美联储 下周 加息 100bp" readOnly />
          <button className="primary-btn">开始检索</button>
        </div>

        <div className="mini-grid">
          {streams.map((s) => (
            <div key={s.platform} className="mini-card">
              <span>{s.platform}</span>
              <strong>{s.count}</strong>
              <p>{s.state}</p>
            </div>
          ))}
        </div>

        <div className="table-card">
          <div className="table-head">
            <span>时间</span><span>来源</span><span>内容</span><span>标签</span>
          </div>
          {rows.map((r) => (
            <div key={r.join('-')} className="table-row">
              <span>{r[0]}</span><span>{r[1]}</span><span>{r[2]}</span><span>{r[3]}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
