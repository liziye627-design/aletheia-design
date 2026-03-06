# Playwright 验证墙收敛策略（参考 browser-use）

## 结论
- 验证墙/登录墙是当前 Agent 失败主因，不能指望纯无状态自动化稳定穿透。
- 采用“登录态持久化 + 阻断即降级 + 证据仓兜底”是可落地、合规且稳定的路径。

## 已落地能力
- `api/v1/endpoints/multiplatform.py` 的 `/playwright-orchestrate` 已支持：
  - `storage_state_map`（按平台传登录态）
  - `PLAYWRIGHT_STORAGE_STATE_<PLATFORM>` 环境变量读取
- `scripts/save_storage_state.py` 可人工完成登录后保存状态。
- `ConcurrentAgentManager` 已输出 `BLOCKED/SELECTOR_MISS/EMPTY_RESULT` 诊断并给出降级建议。

## 推荐运行方式
1. 先生成登录态
```bash
cd /home/llwxy/aletheia/design/aletheia-backend
PYTHONPATH=. ./venv/bin/python scripts/save_storage_state.py --platform zhihu --out state/zhihu.json
PYTHONPATH=. ./venv/bin/python scripts/save_storage_state.py --platform douyin --out state/douyin.json
PYTHONPATH=. ./venv/bin/python scripts/save_storage_state.py --platform xiaohongshu --out state/xiaohongshu.json
```

2. 配置环境变量（示例）
```bash
export PLAYWRIGHT_STORAGE_STATE_ZHIHU=/home/llwxy/aletheia/design/aletheia-backend/state/zhihu.json
export PLAYWRIGHT_STORAGE_STATE_DOUYIN=/home/llwxy/aletheia/design/aletheia-backend/state/douyin.json
export PLAYWRIGHT_STORAGE_STATE_XIAOHONGSHU=/home/llwxy/aletheia/design/aletheia-backend/state/xiaohongshu.json
```

3. 运行诊断
```bash
cd /home/llwxy/aletheia/design/aletheia-backend
PYTHONPATH=. ./venv/bin/python scripts/playwright_diagnostics_report.py --keyword gpt \
  --json-out /home/llwxy/aletheia/design/playwright-agent-probe-gpt-latest.json \
  --md-out /home/llwxy/aletheia/design/playwright-agent-probe-gpt-latest.md
```

## 后续增强（下一步）
- 增加“手动接管模式”：遇到验证墙时暂停并允许人工完成验证后恢复。
- 给 `BLOCKED` 平台加自动截图与 HTML 快照归档，提升选择器维护效率。
- 在编排层加入“Playwright成功率阈值”，低于阈值自动切换稳定信源池。
