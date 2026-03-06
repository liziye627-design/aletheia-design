# 平台修复状态（ZH Core）

- 报告: `docs/source-health-report-zh-core-20260304-r2.json`
- Query: `苏炳添退役了吗`
- Platforms with evidence: **5/9**

## 已修好（可稳定输出正相关）

| Platform | Evidence | Items | Reason | P50(ms) | Primary |
|---|---:|---:|---|---:|---|
| peoples_daily | 5 | 5 | RSS_EMERGENCY_FALLBACK | 55509 | https://www.people.com.cn/rss/politics.xml |
| rss_pool | 1 | 1 | RSS_EMERGENCY_FALLBACK | 36489 | http://www.people.com.cn/rss/ywkx.xml |
| weibo | 20 | 20 | WEB_FALLBACK | 18895 | https://weibo.com/ajax/side/hotSearch |
| xinhua | 2 | 2 | RSS_EMERGENCY_FALLBACK | 18876 | https://www.news.cn/politics/ |
| zhihu | 20 | 20 | WEB_FALLBACK | 15056 | - |

## 仍有问题（0 正相关）

| Platform | Evidence | Items | Reason | P50(ms) | 需要你提供的信息 |
|---|---:|---:|---|---:|---|
| china_gov | 0 | 0 | FALLBACK_EMPTY | 26625 | 确认 gov.cn 是否允许当前出口访问；可选提供更多可检索栏目RSS |
| csrc | 0 | 0 | FALLBACK_EMPTY | 20989 | 提供可稳定访问 csrc.gov.cn 的代理出口；可选提供官方检索入口URL |
| nhc | 0 | 0 | FALLBACK_EMPTY | 18350 | 提供可稳定访问 nhc.gov.cn 的代理出口；可选提供可抓取栏目页 |
| samr | 0 | 0 | FALLBACK_EMPTY | 20560 | 提供可稳定访问 samr.gov.cn 的代理出口，或提供可用栏目页/RSS地址 |

## 下一步（我可直接继续执行）

1. 先修 `china_gov/samr/csrc/nhc`：改成“列表页增量抓取 -> 本地索引检索”，关闭查询时热榜/通用流回退。
2. 对这四个平台单独做 3 轮稳定性探测，输出 success_rate/evidence_rate/timeout_rate。
3. 合并回 `trusted_platforms.auto.json`，仅保留 evidence_rate>0 的平台进主证据链。