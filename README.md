# Aletheia

面向舆情与事实核验场景的一体化调查系统（Backend + Frontend + 多源采集）。

## 项目背景

在热点事件中，常见问题不是“信息太少”，而是“信息太乱”：  
来源多、重复高、噪声大、时间线混乱，导致核验成本高、结论可信度低。

Aletheia 的目标是把调查流程产品化：从线索采集、证据筛选、阶段化分析到报告输出，形成可复用、可追溯、可评估的工作流。

## 解决的问题

- 多源信息难以统一归并，人工筛选成本高。
- 证据相关度与可信度不稳定，结论容易被噪声干扰。
- 调查过程黑盒化，阶段输出无法量化评估。
- 前后端协作链路不完整，运行状态与质量门控不可见。

## 核心能力

- 阶段化调查引擎：按阶段推进调查任务并输出结构化结果。
- 证据质量控制：相关度过滤、证据排序、阶段质量门控。
- 舆情风险分析：支持舆情监测状态与风险信息进入运行时结果。
- 实时运行可视化：前端展示调查进度、阶段状态、验证结果与报告视图。
- 多平台采集扩展：通过 sidecar 能力接入外部采集链路。

## 架构与目录

- `aletheia-backend/`：FastAPI 后端，调查引擎、API、质量门控、舆情分析等核心能力。
- `frontend/`：Web 前端，调查流程页面、验证展示、报告展示与 E2E 用例。
- `core-components/`：核心组件打包与复用目录（用于统一核心能力交付）。
- `aletheia-mobile/`：移动端相关代码。
- `docs/`：说明文档与运维/集成指南。
- `scripts/`：启动、停止、环境准备脚本。

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

## 开源参考与合规

你提到的这段“本项目参考了 xxx”是否需要保留，规则如下：

- 如果直接复用或改写了对方代码：建议保留，并在文档中写清引用来源与许可证信息。
- 如果只是思路参考、未使用代码：可不写在主 README，可放到 `docs/` 的“设计参考”章节。

建议做法：  
在 README 保留简短“致谢/参考”段，在 `docs/OPEN_SOURCE_ATTRIBUTION.md` 维护完整清单（项目名、链接、许可证、使用范围）。
