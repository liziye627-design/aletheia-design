# Aletheia 项目结构与运行核心逻辑

## 1) 当前推荐目录分层（根目录）

- `aletheia-backend/`：FastAPI 后端主服务（核心业务）
- `frontend/`：Web 前端（当前主线：`index.html + src/main.js`）
- `MediaCrawler/`：社交平台增强采集 sidecar
- `aletheia-mobile/`：移动端工程（独立）
- `changes/`：变更记录与执行日志
- `scripts/`：统一启动/停止/连通性脚本
  - `scripts/legacy/`：历史启动脚本归档（不作为默认入口）
- `docs/`：项目结构、流程与操作文档
- `runtime/`：运行期产物（日志/PID/临时报告）

## 2) 后端核心文件与职责

### API 入口层
- `aletheia-backend/main.py`
  - 启动 FastAPI、注册路由、生命周期管理
- `aletheia-backend/api/v1/endpoints/investigations.py`
  - 核验主入口：
    - `POST /api/v1/investigations/preview`
    - `POST /api/v1/investigations/run`
    - `GET /api/v1/investigations/{run_id}`
    - `GET /api/v1/investigations/{run_id}/stream`

### 编排与运行态
- `aletheia-backend/services/investigation_runtime.py`
  - run/preview 内存态、SSE事件缓存、TTL、指标统计
- `aletheia-backend/services/investigation_preview.py`
  - 轻量预分析（不抓取）：意图摘要、主张草案、选源计划、风险提示
- `aletheia-backend/services/investigation_engine.py`
  - 正式执行主链路：采集、过滤、证据分层、主张判定、报告组装

### 核心能力模块
- `aletheia-backend/services/source_planner.py`
  - 自动选源策略（must/candidate/excluded）
- `aletheia-backend/services/investigation_claims.py`
  - 主张拆解、主张级分析与推理文本
- `aletheia-backend/services/opinion_monitoring.py`
  - 评论抓取、可疑评论识别、水军风险统计
- `aletheia-backend/services/layer1_perception/crawler_manager.py`
  - 多平台采集调度与 fallback 策略
- `aletheia-backend/services/external/mediacrawler_client.py`
  - Sidecar API 对接（社交平台增强采集）

### 配置与存储
- `aletheia-backend/core/config.py`
  - 全局配置与 feature flag
- `aletheia-backend/core/sqlite_database.py`
  - SQLite 持久化（run/report payload）

## 3) 前端核心文件与职责

- `frontend/index.html`
  - 页面结构与各大面板容器（核验、报告、我的、信息流、可视化）
- `frontend/src/main.js`
  - 主状态机与数据流：
    - 阶段1：`preview`（可编辑主张/平台）
    - 阶段2：`confirm -> run`（SSE流式执行）
  - 负责树状流程、证据面板、主张分析、导出、历史报告联动
- `frontend/src/styles.css`
  - 视觉布局、树状节点、面板样式、响应式规则

## 4) 系统运行主链路（两阶段）

1. 用户输入主张 -> 前端调用 `POST /investigations/preview`
2. 后端返回：意图摘要 + 主张草案 + 选源计划 + 风险提示
3. 用户确认并可编辑（主张/平台）
4. 前端调用 `POST /investigations/run`（携带 `confirmed_preview_id / confirmed_claims / confirmed_platforms`）
5. 后端异步执行调查引擎，前端通过 `stream` 实时接收SSE并更新树状流程
6. 任务结束后前端拉取最终 `GET /investigations/{run_id}` 渲染完整报告

## 5) 建议运行方式（统一脚本）

- 启动：`./scripts/start-dev.sh`
- 停止：`./scripts/stop-dev.sh`
- 健康检查：`curl -s http://127.0.0.1:8000/health`
- API 前缀：`/api/v1`
- 前端地址：`http://127.0.0.1:5173`

> 已统一：脚本运行日志和 PID 默认写入 `runtime/logs/` 与 `runtime/pids/`，避免根目录持续变脏。

## 6) 这次清理处理说明

- 已清理：根目录临时 PID/日志文件、测试覆盖产物、构建产物与缓存目录
- 保留：业务代码、配置模板、变更记录、设计源文件与核心文档

## 7) 运行主链路与关键文件映射（可直接排障）

### A. 启动阶段
1. `scripts/start-dev.sh`
   - 拉起后端：`aletheia-backend/main.py`
   - 拉起前端：`frontend` (Vite dev server)
   - 写入运行态：`runtime/logs/*.log`、`runtime/pids/*.pid`

### B. 预分析阶段（轻量，不抓取）
1. 前端入口：`frontend/src/main.js`（preview submit）
2. 后端接口：`aletheia-backend/api/v1/endpoints/investigations.py` (`POST /investigations/preview`)
3. 后端服务：`aletheia-backend/services/investigation_preview.py`
4. 运行态缓存：`aletheia-backend/services/investigation_runtime.py`

### C. 正式执行阶段（流式）
1. 前端确认执行：`frontend/src/main.js` (`POST /investigations/run`)
2. 后端主编排：`aletheia-backend/services/investigation_engine.py`
3. 选源策略：`aletheia-backend/services/source_planner.py`
4. 平台抓取：`aletheia-backend/services/layer1_perception/crawler_manager.py`
5. 主张分析：`aletheia-backend/services/investigation_claims.py`
6. 评论与水军风险：`aletheia-backend/services/opinion_monitoring.py`
7. SSE 输出：`GET /investigations/{run_id}/stream`

### D. 结果持久化与展示
1. 存储层：`aletheia-backend/core/sqlite_database.py` (`aletheia-backend/aletheia.db`)
2. 查询接口：`GET /investigations/{run_id}`、`GET /reports/`
3. 前端渲染：`frontend/src/main.js` + `frontend/src/styles.css`

## 8) 日常开发约定（避免再次混乱）

1. 新文档统一放 `docs/guides/`，引用图片放 `docs/assets/`。
2. 新脚本优先放 `scripts/`，历史脚本放 `scripts/legacy/`。
3. 运行产物统一写入 `runtime/`，不要再落在根目录。
4. 功能变更记录统一写入 `changes/` 并同步 `changes/CHANGELOG.md`。
