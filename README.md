# Aletheia

面向舆情与事实核验场景的一体化调查系统（Backend + Frontend + 多源采集）。

## 项目背景

AI 生成内容正在快速放大信息污染：低成本批量生产、跨平台扩散、真假混杂。  
企业与政府在发布与传播环节面临更高的真实性风险，传统新闻采编也面临工作流转型压力。

Aletheia 的目标是把“真实性保障”变成可执行系统：从线索采集、证据筛选、阶段化分析到报告输出，形成可复用、可追溯、可评估的工作流。

## 我们要解决什么

- AI 造假内容大量出现，人工核验无法覆盖传播速度。
- 企业/政府在对外传播中缺少“上线前可审计”的真实性保障流程。
- 用户获取资讯路径从 SEO 向 GEO 迁移：越来越多人直接向 AI 询问实时信息。
- 传统新闻工作者需要新的工作方式：从“写完发布”转向“持续验证 + 可机器传播的可信事实”。

## 项目价值定位

- `面向企业/政府`：降低错误传播与舆情反噬风险，提升对外信息可信度。
- `面向媒体与新闻工作者`：提供面向 AI 时代的核验与发布工作流。
- `面向 GEO 场景`：让高可信信息可被 AI 实时引用与传播，而不是被低质量噪声占据。

## 核心能力

- 阶段化调查引擎：按阶段推进调查任务并输出结构化结果。
- 证据质量控制：相关度过滤、证据排序、阶段质量门控。
- 舆情风险分析：支持舆情监测状态与风险信息进入运行时结果。
- 实时运行可视化：前端展示调查进度、阶段状态、验证结果与报告视图。
- 多平台采集扩展：通过 sidecar 能力接入外部采集链路。

## 架构与目录

- `aletheia-backend/`：FastAPI 后端，调查引擎、API、质量门控、舆情分析等核心能力。
- `frontend/`：Web 前端，调查流程页面、验证展示、报告展示与 E2E 用例。
- `aletheia-mobile/`：移动端相关代码。
- `docs/`：说明文档与运维/集成指南。
- `scripts/`：启动、停止、环境准备脚本。
- `archive/`：历史与归档内容（当前包含 `.kiro` 与 `core-components`）。

## 快速开始

### 1) 启动（推荐）

```bash
cd /home/llwxy/aletheia/design
./scripts/start-dev.sh
```

停止：

```bash
./scripts/stop-dev.sh
```

### 2) 分别启动

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

### 3) 默认访问地址

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

## 开发与测试

后端示例测试：

```bash
cd /home/llwxy/aletheia/design/aletheia-backend
./venv/bin/pytest -q tests/unit/test_crawler_manager_quality.py tests/unit/test_external_search_pipeline.py tests/unit/test_investigation_engine.py
```

前端测试与构建：

```bash
cd /home/llwxy/aletheia/design/frontend
npm run test:unit
npm run test:e2e
npm run build
```

## 安全说明

- 严禁提交 `.env`、API Key、Token、Cookie、私钥等敏感信息。
- 若密钥曾进入 Git 历史，必须立刻轮换并清理分支/历史。
- 提交前建议执行最小检查：`git status`、`git diff --cached`、密钥扫描。
