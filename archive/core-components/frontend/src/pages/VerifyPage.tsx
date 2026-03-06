const queue = [
  ['intel_01', '交叉验证中', 'Step 5/8', '00:01.8'],
  ['intel_02', '异常检测中', 'Step 6/8', '00:00.9'],
  ['intel_03', '待执行', 'Step 1/8', '--'],
]

const checklist = [
  '物理层检验失败时触发低分短路',
  '逻辑层谬误按规则扣分',
  '信源分析融合账号元数据',
  'cross_sources 触发多源交叉验证',
  'Layer2 异常检测接入最终评分',
]

export default function VerifyPage() {
  return (
    <>
      <section className="head-row">
        <div>
          <h1>可信核验</h1>
          <p>与后端 enhanced_cot_engine 八阶段严格对齐</p>
        </div>
      </section>

      <section className="panel verify-layout">
        <div className="insight-card">
          <h3>核验任务队列</h3>
          <div className="table-head"><span>ID</span><span>状态</span><span>阶段</span><span>耗时</span></div>
          {queue.map((q) => (
            <div key={q[0]} className="table-row"><span>{q[0]}</span><span>{q[1]}</span><span>{q[2]}</span><span>{q[3]}</span></div>
          ))}
        </div>

        <div className="insight-card">
          <h3>后端逻辑清单</h3>
          {checklist.map((item) => <div key={item} className="tag action">{item}</div>)}
        </div>
      </section>
    </>
  )
}
