import { useEffect, useMemo, useState } from 'react'

type StepDef = { id: number; title: string; detail: string; impact: number }
type FeedItem = { step: number; time: string; text: string; tone?: 'normal' | 'alert' | 'active' }

const STEPS: StepDef[] = [
  { id: 1, title: '预处理', detail: '剥离情绪词并提取可验证主张', impact: 0 },
  { id: 2, title: '物理层检验', detail: '检查时间/地点/物理规律一致性', impact: 0 },
  { id: 3, title: '逻辑层检验', detail: '识别推断跳跃与逻辑谬误', impact: -0.15 },
  { id: 4, title: '信源分析', detail: '账号画像与传播结构评分', impact: -0.2 },
  { id: 5, title: '交叉验证', detail: '多源事实一致性比对', impact: 0.08 },
  { id: 6, title: '异常检测', detail: 'Layer2 检测协同传播信号', impact: -0.1 },
  { id: 7, title: '证据综合', detail: '支持证据与疑点汇总', impact: 0 },
  { id: 8, title: '自我反思/终判', detail: '偏见校正并输出 final_score', impact: -0.02 },
]

const FEED_STREAM: FeedItem[] = [
  { step: 1, time: '10:21:03', text: '文本清洗完成，提取核心主张 3 条' },
  { step: 2, time: '10:21:04', text: '时空约束通过，未发现明显物理冲突' },
  { step: 3, time: '10:21:05', text: '检测到推断跳跃，逻辑扣分 -0.15', tone: 'alert' },
  { step: 4, time: '10:21:05', text: '账号新注册且单源扩散，信源扣分 -0.20', tone: 'alert' },
  { step: 5, time: '10:21:06', text: '命中首发帖文 @macro_watch', tone: 'active' },
  { step: 5, time: '10:21:07', text: 'Reuters: 未见 100bp 官方安排' },
  { step: 5, time: '10:21:08', text: 'Fed: 当前区间不支持该说法' },
  { step: 6, time: '10:21:09', text: '发现同模板传播簇，异常信号触发', tone: 'alert' },
  { step: 7, time: '10:21:10', text: '证据综合完成，支持疑点比 2:5' },
  { step: 8, time: '10:21:11', text: '终判完成：FALSE / 虚假，建议限流处置', tone: 'active' },
]

export default function ReportPage() {
  const [currentStep, setCurrentStep] = useState(5)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= 8) {
          setRunning(false)
          return 8
        }
        return prev + 1
      })
    }, 1800)
    return () => window.clearInterval(timer)
  }, [running])

  const score = useMemo(() => {
    const impact = STEPS.filter((s) => s.id <= currentStep).reduce((sum, s) => sum + s.impact, 0)
    return Math.max(0, Math.min(1, 0.5 + impact))
  }, [currentStep])

  const visibleFeeds = useMemo(() => FEED_STREAM.filter((f) => f.step <= currentStep).slice(-6), [currentStep])
  const riskLabel = score < 0.2 ? '高风险传播' : score < 0.4 ? '中风险传播' : '低风险传播'
  const verdict = currentStep >= 8 ? (score < 0.4 ? 'FALSE / 虚假' : 'MIXED / 待定') : '判定进行中'

  return (
    <>
      <section className="head-row">
        <div>
          <h1>核验报告</h1>
          <p>多源交叉验证后的风险画像与处置建议</p>
        </div>
        <div className="progress-ops">
          <button className="ghost-btn" onClick={() => setRunning((v) => !v)}>{running ? '暂停流程' : '继续流程'}</button>
          <button className="ghost-btn" onClick={() => setCurrentStep(1)}>重置到 Step1</button>
        </div>
      </section>

      <section className="panel">
        <div className="metrics-grid">
          <div className="metric danger"><span>可靠度</span><strong>{Math.round(score * 100)}% · 极低</strong></div>
          <div className="metric warn"><span>风险等级</span><strong>{riskLabel}</strong></div>
          <div className="metric source"><span>首发信源 · X</span><strong>@macro_watch · 2h</strong></div>
        </div>

        <div className="flow-card">
          <div className="flow-head"><h2>真相河流 · 渐进执行视图</h2><span>当前执行进度：Step {currentStep} / 8</span></div>
          <div className="step-chips">
            {STEPS.map((step) => {
              const done = step.id < currentStep
              const active = step.id === currentStep
              return <div key={step.id} className={`chip ${done ? 'chip-done' : active ? 'chip-active' : ''}`}>{step.id}.{step.title} {done ? '✓' : active ? '进行中' : '待执行'}</div>
            })}
          </div>

          <div className="flow-core">
            <div className="claim-block"><span>CLAIM</span><p>网传：美联储下周加息 100bp</p></div>
            <div className="river-line">
              {STEPS.slice(0, 6).map((s) => <div key={s.id} className={`node ${s.id < currentStep ? 'done' : s.id === currentStep ? 'active' : ''}`}>{s.id}</div>)}
            </div>
            <div className="branches">
              <div className="branch branch-top">首发信源快照（Step4）</div>
              <div className="branch branch-top verify">Reuters 核查（Verified）</div>
              <div className="branch">协同传播聚合 +3</div>
              <div className="branch">联储数据源</div>
            </div>
            <div className="verdict-block"><span>FINAL</span><strong>{verdict}</strong><button className="primary-btn small">生成报告</button></div>
          </div>

          <div className="details-grid">
            {STEPS.map((s) => <div key={s.id} className={`detail-item ${s.id === currentStep ? 'detail-active' : ''}`}>S{s.id} {s.title}：{s.detail}</div>)}
          </div>
        </div>

        <div className="insight-grid">
          <div className="insight-card">
            <h3>实时资讯检索流</h3>
            {visibleFeeds.map((feed, idx) => (
              <div key={`${feed.time}-${idx}`} className={`feed-row ${feed.tone ?? 'normal'}`}><span>{feed.time}</span><p>{feed.text}</p></div>
            ))}
          </div>

          <div className="insight-card">
            <h3>证据权重面板</h3>
            {STEPS.map((s) => (
              <div key={s.id} className="weight-row"><span>S{s.id} {s.title}</span><strong className={s.impact >= 0 ? 'plus' : 'minus'}>{s.impact >= 0 ? '+' : ''}{s.impact.toFixed(2)}</strong></div>
            ))}
            <div className="sum-row">当前累计分：{score.toFixed(2)}</div>
          </div>

          <div className="insight-card">
            <h3>一致性/冲突追踪</h3>
            <div className="tag ok">一致：权威源均不支持核心主张</div>
            <div className="tag bad">冲突：社媒帖文与权威结论矛盾</div>
            <div className="tag pending">待确认：是否存在二次剪辑</div>
            <div className="tag action">点击冲突项可打开证据对照弹窗</div>
          </div>
        </div>
      </section>
    </>
  )
}
