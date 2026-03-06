# Aletheia 当前系统技术方案（2026-02-23）

## 1. 目标与定位

Aletheia 当前版本定位为“多源取证 + 多阶段推理 + 可解释报告”的信息核验系统。  
核心目标是把“输入一条主张”转换为“可追溯证据、可信度评估、处置建议、可导出报告”。

系统强调两件事：

1. 证据链可追溯（来源、URL、时间、验证状态）
2. 结果可解释（阶段化流程、降级原因、诊断字段）

## 2. 系统边界与模块

### 2.1 后端（FastAPI）

入口：`main.py`  
API 聚合：`api/v1/router.py`

当前对外主能力：

1. `investigations`：编排式全链路核验（run/stream/result/diagnostics）
2. `multiplatform`：多平台检索与渲染抽取（含 Playwright 渲染后提取）
3. `reports`：报告写入与导出
4. `intel`/`intel_enhanced`/`vision`/`feeds`：保留的补充能力接口

核心引擎：

1. `services/investigation_engine.py`：主编排器（增强推理 → 多平台检索 → 严格验证 → 多 Agent 综合 → 报告渲染）
2. `services/layer1_perception/crawler_manager.py`：平台抓取与回退策略
3. `services/multi_agent_siliconflow.py`：证据仓驱动的多 Agent 综合分析（SiliconFlow）
4. `services/report_template_service.py`：报告模板加载与渲染

存储与状态：

1. `core/sqlite_database.py`：SQLite 持久化
2. 关键表：`intel`、`reports`、`investigation_runs`、`evidence_cache`

### 2.2 前端（Vite）

当前在线主界面使用：`frontend/index.html` + `frontend/src/main.js`（原生 DOM + SSE）  
页面包括四个主标签：急救核验、证据报告、信息流、可视化。

交互链路：

1. 创建任务：`POST /api/v1/investigations/run`
2. 过程流：`GET /api/v1/investigations/{run_id}/stream`（SSE）
3. 完成拉取：`GET /api/v1/investigations/{run_id}`
4. 侧链渲染抽取：`POST /api/v1/multiplatform/playwright-rendered-extract`
5. 报告写入/导出：`/api/v1/reports/*`

## 3. 当前主流程（一次核验）

1. 前端提交 claim/keyword/platforms 与运行参数
2. 后端创建 run（状态 queued），异步执行 orchestrator
3. 阶段执行（标准 6~7 步）：
   1. enhanced_reasoning
   2. multiplatform_search
   3. cross_platform_credibility
   4. multi_agent
   5. external_sources（可降级）
   6. report_template_render
4. 后端通过 SSE 推送 `step_update/evidence_found/data_progress/warning`
5. 前端消费 SSE 实时展示进度与证据
6. 任务结束后前端拉取最终结果并渲染报告、证据筛选、可视化

## 4. 已完成的后端清理（本次）

### 4.1 代码层清理（已删除）

以下历史双工分支代码在当前主流程中无运行引用，已删除：

1. `services/layer1_perception/duplex_system.py`
2. `services/layer1_perception/hybrid_manager.py`
3. `services/layer1_perception/multi_agent_orchestrator.py`
4. `services/layer3_reasoning/enhanced_cot_engine.py`（当前未被任何运行链路引用）

同时删除了对应历史演示文件：

1. `demo_full_system.py`
2. `demo_llm_enhanced_system.py`
3. `demo_script.sh`
4. `services/agent_framework/demo.py`
5. `optimize.sh`（会覆盖现有 endpoints 导出，已不适配当前架构）

并删除了已失效的双工架构文档：

1. `DUPLEX_MULTI_AGENT_ARCHITECTURE.md`

### 4.2 产物层清理（已删除）

1. backend 历史覆盖与缓存产物（`.coverage`、`.pytest_cache`、`.hypothesis`、`htmlcov`）
2. backend 历史日志文件（`logs/*.log*`）
3. 项目根目录历史运行快照/截图/探针输出（e2e 图片、investigation/probe/source/playwright-agent-probe 等）

### 4.3 证据量策略调整（本次）

为解决“默认只拿到约 10 条证据、展示可信度偏弱”的问题，已将默认采集策略上调：

1. 前端 `buildInvestigationTuning`：目标有效证据由 16~24 提升至 40~60，实时证据目标由 4~5 提升至 15~20，运行预算与 phase1 截止同步提高
2. 前端请求 `limit_per_platform` 从 20 提升到 40
3. 后端 `InvestigationRunRequest.live_evidence_target` 默认值由 10 提升至 30
4. 后端配置新增 `INVESTIGATION_LIVE_EVIDENCE_TARGET=30` 作为统一默认

### 4.4 Investigation 引擎结构拆分（第一阶段）

在不改变行为的前提下，已完成“按职责拆分”：

1. `services/investigation_helpers.py`：常量、时间/URL/相关度等通用函数
2. `services/investigation_runtime.py`：`InvestigationRunManager` 运行态与持久化管理
3. `services/investigation_reporting.py`：结果状态判定、双画像评分、外部信源检查、报告章节渲染
4. `services/investigation_engine.py`：保留 orchestrator 主流程，改为调用上述模块（编排职责更聚焦）

收益：

1. 主文件行数显著下降，阅读与定位成本降低
2. 运行态/工具函数/报告渲染边界更清晰，便于后续继续拆 `execute` 主流程
3. 对外接口保持不变，现有前端与 API 调用无需改造

## 5. 当前适用应用场景

1. 突发舆情/谣言核验：快速形成“证据 + 风险 + 建议”简报
2. 政务/企业应急研判：要求可解释、可归档、可导出的核验结果
3. 多源信息交叉复核：国际媒体 + 官方信源 + 社区来源混合场景
4. 业务运营事实核验：针对特定 claim 的周期性复跑与证据缓存对比

## 6. 当前项目存在的问题与改进方案

### 问题 1：编排器文件过大、职责耦合重

现状：`services/investigation_engine.py` 已非常庞大，检索、验证、回填、评分、事件流、报告组装耦合在一个文件。  
风险：维护成本高，缺陷定位慢，回归测试覆盖困难。

方案：

1. 拆分为 4 个子模块：`search_pipeline`、`validation_pipeline`、`synthesis_pipeline`、`report_pipeline`
2. 保留 orchestrator 只做阶段调度与状态流转
3. 为每个子模块建立独立单测与契约测试

### 问题 2：前端存在“双栈并存”风险

现状：`src/main.js`（当前在用）与 React 体系（`main.tsx`/`App.tsx`）并存。  
风险：未来迭代可能出现路由/状态/样式与接口行为不一致。

方案：

1. 明确单一生产入口（建议先维持 `main.js` 到提交）
2. 提交后做一次“UI 栈收敛”：统一到 React 或统一到 DOM 方案
3. 在 CI 加入口文件一致性校验

### 问题 3：证据质量与平台覆盖仍受关键词质量影响

现状：宽泛关键词下会出现 `LOW_RELEVANCE` 较高，虽然证据数可达标，但质量波动大。  
风险：报告虽“有量”，但可信度与说服力不足。

方案：

1. 增加 query rewrite（实体、时间、事件三元组扩展）
2. 按平台设置差异化检索模板，降低无关命中
3. 在报告中显式展示“高相关/低相关占比”与降级说明
4. 对“命中条目/可回溯条目”增加平台分布明细，避免用户误判“系统只抓了少量数据”

### 问题 4：部分步骤超时导致最终状态降级为 partial

现状：增强推理、跨平台可信度、外部源检查在预算紧张时常超时。  
风险：用户体验与评审观感受影响（完成但非 complete）。

方案：

1. 设立“演示配置”与“生产配置”两套参数
2. 演示配置提高关键步骤预算并限制并发抖动
3. 超时时输出标准化降级原因与可重试建议

### 问题 5：数据模式异构（不同 crawler 的 URL 字段不统一）

现状：不同平台返回 `url/source_url/original_url/metadata.source_url` 等混用。  
风险：验证阶段误判为空 URL，影响证据留存与覆盖。

方案：

1. 已在编排层引入统一 URL 提取器（已落地）
2. 后续在 crawler 输出层统一 schema，逐步收敛字段
3. 增加 schema contract test 防止回归

### 问题 6：回归测试覆盖深度不足

现状：关键路径单测已具备，但端到端与稳定性回归仍偏少。  
风险：修改阈值/回填策略时容易引入行为漂移。

方案：

1. 增加 investigation 端到端回归集（含 broad keyword 场景）
2. 增加 SSE 事件契约测试（字段完整性、顺序、终态）
3. 将“证据量 + 平台覆盖 + 状态”设为回归门禁指标

## 7. 建议的下一步里程碑

### M1（1~2 天，提交前后）

1. 固化演示参数 profile（减少 partial 触发）
2. 前端报告页补充 validation diagnostics 展示
3. 增加 run 列表 API（便于历史追踪与运营看板）

### M2（1 周）

1. 拆分 investigation_engine 子模块
2. 统一 crawler 输出 schema 与契约测试
3. 收敛前端单一入口栈

### M3（2~3 周）

1. 引入更强的检索策略（query expansion + re-rank）
2. 完整观测体系（Prometheus + run 质量指标看板）
3. 形成稳定“生产配置/演示配置”发布流程

## 8. 当前结论

当前系统已经可以完成“从主张输入到前端可视化与报告导出”的完整闭环，且具备可解释降级能力。  
本次已完成后端历史分支清理与产物清理，提交前建议优先处理“超时导致 partial”与“前端单栈收敛计划”，确保评审表现稳定。
