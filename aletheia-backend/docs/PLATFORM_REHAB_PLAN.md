# Platform Rehab Plan (High-Credibility Evidence Pipeline)

- Version: v1.0
- Created At: 2026-03-03
- Scope: crawler + source routing + evidence gating + health scoring
- Objective: 在事实核查模式下，稳定产出“高可信 + 高相关 + 足量”证据，不依赖热榜兜底。

## 1. Current Baseline

### 1.1 Stable Platforms (Do Not Break)
- `xinhua`
- `the_paper`

### 1.2 Known Problem Platforms
- Media group: `peoples_daily`, `chinanews`, `cctv`, `caixin`
- Official group: `samr`, `csrc`, `nhc`, `mem`, `mps`
- Aggregator group: `rss_pool`

### 1.3 Current Hard Constraints
- Strict mode: no hot榜 fallback for evidence
- Evidence gate: entity+keyword required
- Direct link quality: must be specific URL, not index/home page

## 2. Final Target State

### 2.1 Functional Target
- 中文 query 的主证据池只由中文高可信来源组成。
- 所有结论证据均可追溯到可信域原文。
- 无相关证据时返回“证据不足”，不再以热点替代。

### 2.2 Reliability Target
- P95 单平台检索时延 <= 10s。
- 每日巡检中，主证据池平台 `evidence_items > 0` 比例 >= 70%。
- 无关证据进入 Evidence Pool 的比例 = 0。

### 2.3 Quality Target
- `KeywordHitRate = keyword_hit_items / items >= 0.8`（主平台）
- `EntityHitRate = entity_hit_items / items >= 0.8`（主平台）
- `TrustedHitRate = trusted_hits / items >= 0.9`（主平台）

## 3. Architecture Policy

### 3.1 Two-Pool Strategy
- Evidence Pool: 支撑结论，只允许高可信+强相关证据。
- Context Pool: 背景信息，可展示但不参与结论断言。

### 3.2 Discovery vs Fetch Separation
- Discovery: RSS/sitemap/list-page 只负责发现 URL。
- Fetch: 对原站文章页抓取正文，提取结构化字段后入库。

### 3.3 Search Strategy
- 平台 native search 可用则用。
- 不支持 search 的平台，统一走“增量抓取 + 本地索引检索（local_index_only）”。

## 4. Platform Capability Matrix (To Maintain)

每个平台维护以下字段（单一真相配置）：
- `platform`
- `tier` (`official|major_media|background`)
- `lang` (`zh|en|mixed`)
- `discovery_mode` (`rss|sitemap|list_page|hybrid`)
- `search_mode` (`native|local_index_only|none`)
- `content_mode` (`direct_article|proxy_source_domain`)
- `trusted_domains[]`
- `timeout_ms`
- `retry_policy`
- `enabled_in_evidence_pool` (`true|false`)

## 5. Execution Plan (Phased)

## Phase 0 - Freeze + Guardrail (Day 0)
- Freeze `xinhua`, `the_paper` configs and tests.
- Keep other target platforms in observe/background mode.
- Snapshot runtime config and health report artifacts.

Deliverables:
- `docs/platform-detection-expanded.md` baseline archive
- `docs/source-health-report-evidence.md` baseline archive

Exit criteria:
- `xinhua/the_paper` 连续 3 轮巡检稳定产出证据。

## Phase 1 - Media Group Rehab (Day 1-3)
Platforms:
- `peoples_daily`, `chinanews`, `cctv`, `caixin`

Actions:
- 增加 query-aware RSS feed discovery（site 限定）。
- 若返回为 Google News 路由，必须回填 `source_domain` 并做可信域映射。
- 平台 budget 固定为 8-10s，失败进入 background，不污染 evidence。

Exit criteria:
- 至少 2 个平台达到：`items>=3`, `keyword_hit>=70%`, `entity_hit>=70%`。

## Phase 2 - Official Group Rehab (Day 3-6)
Platforms:
- `samr`, `csrc`, `nhc`, `mem`, `mps`

Actions:
- 明确放弃站内 search 依赖。
- 建立栏目列表增量抓取模板（公告/新闻栏目）。
- 抓正文入库后统一走本地索引检索。

Exit criteria:
- 至少 2 个官方平台在 3 轮巡检中出现 `evidence_items > 0`。

## Phase 3 - rss_pool Rebuild (Day 6-8)
Actions:
- `rss_pool` 改造为 local-first（先查本地索引，再网络补充）。
- `RSS_POOL_SEARCH_SKIP_NETWORK_IF_LOCAL_ENOUGH=true` 生效。
- 热门 query 加强候选召回窗口（lookback, max candidates）。

Exit criteria:
- `rss_pool` P95 <= 10s 且非空率显著提升（>=50% on test set）。

## Phase 4 - Productionization (Day 8-10)
Actions:
- 健康评分完全切换为 evidence-based 口径。
- 自动白名单生成仅基于 `evidence_success_rounds/evidence_items`。
- 平台自动降级与恢复策略上线。

Exit criteria:
- 20 条中文查询集上，Evidence Pool 非空率 >= 70%。

## 6. Detection & Rotation SOP

### 6.1 Detection Job
- Script: `docs/platform-detection-expanded.*` generation workflow
- Frequency: daily 3 rounds
- Query set: sports/public policy/finance/public health/mixed

### 6.2 Platform State Machine
- `active`: evidence_items > 0 且质量指标达标
- `observe`: 有数据但质量未达标
- `degraded`: 连续 2 轮 `evidence_items = 0`
- `disabled`: 连续 3 轮 `evidence_items = 0`

### 6.3 Recovery Rule
- disabled 平台在后续 2 轮 `evidence_items > 0` 自动恢复到 observe。

## 7. Risk Control & Rollback

### 7.1 Rollback Trigger
- 主平台（`xinhua`/`the_paper`）任一出现连续 2 轮全空。
- Evidence Pool 出现无关证据（entity miss）> 0。

### 7.2 Rollback Action
- 恢复到上一版平台配置快照。
- 禁用当日新增平台规则。
- 保留日志与报告用于复盘。

## 8. Ownership & RACI

- Pipeline owner: Backend Crawler Team
- Data quality owner: Investigation/Fact-check Team
- Runtime owner: Ops
- Approval owner: Product/Tech lead

## 9. Weekly Checkpoint Template

- Week: YYYY-MM-DD ~ YYYY-MM-DD
- Added platforms:
- Repaired platforms:
- Disabled platforms:
- Evidence non-empty rate:
- Avg keyword hit rate:
- Avg entity hit rate:
- Avg trusted hit rate:
- Top failure reasons:
- Next-week focus:

## 10. Non-Goals

- 不做绕过登录/验证码/付费墙的抓取。
- 不承诺“全网历史全量抓取”。
- 不用热榜替代事实证据。
