# 平台修复状态（ZH Core）

- 基准关键词: `苏炳添退役了吗`
- 轮次: 1  平台: 9  可产出平台: 3
- 总相关证据: 41

## 已修复/可稳定产出

| 平台 | 当前状态 | 证据数 | P95(ms) | 说明 |
|---|---|---:|---:|---|
| rss_pool | ok / RSS_EMERGENCY_FALLBACK | 1 | 32807 | 可返回正相关证据 |
| weibo | ok / WEB_FALLBACK | 20 | 17002 | 可返回正相关证据 |
| zhihu | ok / WEB_FALLBACK | 20 | 15055 | 可返回正相关证据 |

## 待修复

| 平台 | 当前状态 | 证据数 | P95(ms) | 主要问题 | 建议动作 |
|---|---|---:|---:|---|---|
| china_gov | fallback / FALLBACK_EMPTY | 0 | 16416 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |
| csrc | fallback / FALLBACK_EMPTY | 0 | 35651 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |
| nhc | fallback / FALLBACK_EMPTY | 0 | 19878 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |
| peoples_daily | fallback / FALLBACK_EMPTY | 0 | 55807 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |
| samr | fallback / FALLBACK_EMPTY | 0 | 25931 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |
| xinhua | fallback / FALLBACK_EMPTY | 0 | 55893 | 网络超时+站内检索能力不足 | 提高该平台预算/超时，或切换为本地索引优先 |