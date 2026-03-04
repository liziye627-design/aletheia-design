# Aletheia Workspace

统一工作区入口（后端 + 前端 + MediaCrawler sidecar）。

## 1. 当前架构

- `aletheia-backend/`：主后端（FastAPI，调查引擎、证据筛选、外部搜索、RSS/爬虫编排）
- `frontend/`：Web 前端（展示调查流程、证据、报告）
- `MediaCrawler/`：多平台采集 sidecar（按需由后端自动拉起）
- `scripts/`：开发环境脚本（启动、停止、环境检查）
- `runtime/`：运行时文件（`logs/`、`pids/`）
- `docs/`：项目说明与操作文档
- `archive_external_20260304/`（在上级目录）：外部参考仓库归档

## 2. 启动方式

### 2.1 一键开发启动（推荐）

```bash
cd /home/llwxy/aletheia/design
./scripts/start-dev.sh
```

停止：

```bash
./scripts/stop-dev.sh
```

### 2.2 分别启动

后端：

```bash
cd /home/llwxy/aletheia/design/aletheia-backend
./run-server.sh
```

前端：

```bash
cd /home/llwxy/aletheia/design/frontend
npm run dev
```

## 3. 访问地址

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

## 4. 关键运行说明（当前版本）

- 后端默认开启严格相关度过滤（高到低排序，过滤无关证据）。
- 后端默认启用 MediaCrawler sidecar：
  - `MEDIACRAWLER_ENABLED=true`
  - `MEDIACRAWLER_NONCOMMERCIAL_ACK=true`
  - 默认地址 `http://127.0.0.1:18080`
- 日志目录已统一为：
  - `runtime/logs/`
  - `aletheia-backend/logs/`
  - `MediaCrawler/logs/`

## 5. 目录说明（按用途）

- 业务代码：
  - `aletheia-backend/api`
  - `aletheia-backend/services`
  - `aletheia-backend/core`
  - `frontend/src`
- 配置：
  - `aletheia-backend/.env`
  - `aletheia-backend/.env.example`
  - `frontend/.env`
  - `frontend/.env.example`
- 脚本：
  - `scripts/start-dev.sh`
  - `scripts/stop-dev.sh`
  - `scripts/setup-env.sh`

## 6. 测试与校验

后端核心测试：

```bash
cd /home/llwxy/aletheia/design/aletheia-backend
./venv/bin/pytest -q tests/unit/test_crawler_manager_quality.py tests/unit/test_external_search_pipeline.py tests/unit/test_investigation_engine.py
```

前端构建校验：

```bash
cd /home/llwxy/aletheia/design/frontend
npm run build
```

## 7. 仍可继续优化的点（按优先级）

### P0（建议尽快）

- 把 `design/.git` 从“全量快照式提交”改为“主干精简提交”，减少后续 push 成本。
- 将 `frontend/node_modules` 与 `aletheia-backend/venv` 严格排除在版本控制外（已在子项目 `.gitignore` 中处理，建议再做一次仓库级核查）。
- 给 `MediaCrawler` 增加独立启动脚本与健康探针脚本，避免主后端日志里混杂 sidecar 启停噪声。

### P1（稳定性与维护）

- 拆分后端 README：`部署版`（Docker）与 `开发版`（本地 run-server）分开，避免配置混淆。
- 将运行产物统一收口到 `runtime/`，减少 `aletheia-backend/logs` 与 `MediaCrawler/logs` 的重复。
- 增加每周自动清理脚本（旧日志、旧报告、缓存目录）。

### P2（结构治理）

- 把 `assets/`、`image.png`、`aletheia-ui.pen` 按“设计资产”单独归档到 `design-assets/`。
- 若当前不开发移动端，可将 `aletheia-mobile/` 迁到归档区以减少主工作区噪声。

## 8. 故障排查入口

- 总文档：`docs/PROJECT_STRUCTURE_AND_RUNTIME_FLOW.md`
- 集成说明：`docs/guides/INTEGRATION_GUIDE.md`
- 快速开始：`docs/guides/QUICK_START.md`
- 故障排查：`docs/guides/TROUBLESHOOTING.md`

## 9. 安全与提交建议

- 严禁提交 `.env`、API key、浏览器登录态。
- 提交前建议执行：
  - `git status`
  - `git diff --cached`
  - 密钥扫描（正则扫描 `sk-`、`Bearer`、`API_KEY`）
