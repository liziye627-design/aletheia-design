# Platform Acceptance Checklist

- Version: v1.0
- Created At: 2026-03-03
- Purpose: 平台接入与修复后的统一验收标准（功能/质量/稳定性/回滚）

## 1. Pre-Check (Before Testing)

- [ ] `.env` 已配置并可读取。
- [ ] 代理配置一致（`HTTPX_TRUST_ENV_ONLY=true`）。
- [ ] 数据库可写，`rss_articles` 可读写。
- [ ] 严格模式开启（禁止热榜替代证据）。
- [ ] 最新检测脚本与健康报告可执行。

## 2. Platform Functional Acceptance

对每个平台逐条检查：

- [ ] 能返回结构化字段：`title/url/published_at/source`。
- [ ] `metadata.retrieval_mode` 正确。
- [ ] `metadata.source_domain` 可用（如经 Google News 路由必须有 source_domain）。
- [ ] 结果 URL 可追溯到可信来源域。
- [ ] 非相关内容不会进入 Evidence Pool。

## 3. Relevance & Trust Acceptance

测试 query 使用至少 10 条中文事实核查问题。

每个平台需统计：
- `items`
- `keyword_hit_items`
- `entity_hit_items`
- `trusted_hits`

通过标准（主证据平台）：
- [ ] `items >= 3`
- [ ] `keyword_hit_items / items >= 0.8`
- [ ] `entity_hit_items / items >= 0.8`
- [ ] `trusted_hits / items >= 0.9`

通过标准（观察平台）：
- [ ] `items >= 1`
- [ ] `keyword_hit_items / items >= 0.5`
- [ ] `entity_hit_items / items >= 0.5`

## 4. Latency & Stability Acceptance

- [ ] 单平台 `P95 latency <= 10s`。
- [ ] 连续 3 轮检测无崩溃。
- [ ] 连续 3 轮中至少 2 轮 `evidence_items > 0`（主平台）。
- [ ] 无大量 `ConnectTimeout` 风暴（同平台同轮 >70%）。

## 5. Evidence Pool Integrity

- [ ] Evidence Pool 中所有条目均 `entity_hit=true`。
- [ ] Evidence Pool 中所有条目均 `trusted_domain=true`。
- [ ] Context Pool 条目不会参与最终结论。
- [ ] 若 Evidence Pool 为空，结果为 `insufficient_evidence`。

## 6. Health Report Acceptance

- [ ] `source-health-report-evidence.json` 已生成。
- [ ] 口径使用 `evidence_items/evidence_success_rounds`。
- [ ] auto whitelist 由 evidence 口径生成。
- [ ] 白名单未包含连续空证据的平台。

## 7. Regression Checklist

每次修复后都要回归：

- [ ] `xinhua` 仍稳定可用。
- [ ] `the_paper` 仍稳定可用。
- [ ] 新增平台不会降低已有平台成功率。
- [ ] 无关证据入池率仍为 0。

## 8. Rollback Readiness

- [ ] 有上一版配置快照。
- [ ] 有一键回滚脚本/步骤文档。
- [ ] 回滚后 `xinhua/the_paper` 可立即恢复。

## 9. Final Go/No-Go Decision

Go 条件（全部满足）：
- [ ] 主平台数 >= 3（含现有稳定平台）
- [ ] 20 条查询中 `Evidence Pool 非空率 >= 70%`
- [ ] `无关证据入池率 = 0`
- [ ] `P95 latency <= 10s`

No-Go 任一触发：
- [ ] 主平台连续 2 轮全空
- [ ] Evidence Pool 出现 entity miss
- [ ] trusted hit 比例低于 80%

## 10. Evidence for Sign-off

发布验收时需附：
- [ ] `docs/platform-detection-expanded.md`
- [ ] `docs/source-health-report-evidence.md`
- [ ] 白名单生成文件（auto）
- [ ] 样例查询证据截图/日志摘要
