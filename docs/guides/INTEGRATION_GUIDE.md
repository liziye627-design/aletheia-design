# Aletheia 前后端集成指南

本指南说明如何配置、启动和测试Aletheia前后端集成。

## 📋 前置条件

在开始之前，请确保您的系统满足以下要求：

### 必需软件

- ✅ **Node.js 18+** - 前端开发环境
  - 检查: `node --version`
  - 下载: https://nodejs.org/

- ✅ **Python 3.10+** - 后端开发环境
  - 检查: `python3 --version`
  - 下载: https://www.python.org/

- ✅ **npm** - Node包管理器（通常随Node.js安装）
  - 检查: `npm --version`

- ✅ **Git** - 版本控制（可选，用于克隆项目）
  - 检查: `git --version`

### 系统要求

- 操作系统: Linux, macOS, 或 Windows (WSL2)
- 内存: 至少 4GB RAM
- 磁盘空间: 至少 2GB 可用空间

## 🚀 快速开始

### 1. 环境配置

首先运行环境配置脚本，它会自动创建和验证前后端的环境变量文件：

```bash
./scripts/setup-env.sh
```

这个脚本会：
- 检查前后端 `.env` 文件是否存在
- 从 `.env.example` 创建 `.env` 文件（如果不存在）
- 验证必需的配置项
- 提供缺失配置的清晰提示

#### 前端配置 (frontend/.env)

```env
# API 基础地址
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

#### 后端配置 (aletheia-backend/.env)

后端需要配置至少一个LLM API Key：

```env
# SiliconFlow (推荐)
SILICONFLOW_API_KEY=your_key_here

# 或者 OpenAI
OPENAI_API_KEY=your_key_here

# 或者 Kimi
KIMI_API_KEY=your_key_here

# 或者 DashScope(OpenAI兼容，coding域名)
STEPFUN_API_KEY=your_key_here
STEPFUN_API_BASE=https://coding.dashscope.aliyuncs.com/v1
STEPFUN_SMALL_MODEL=qwen3-coder-plus
STEPFUN_LARGE_MODEL=qwen3-max-2026-01-23
SILICONFLOW_PREFERRED=True

# CORS配置（已默认包含前端端口）
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://127.0.0.1:5173"]
```

LLM 路由约定（当前项目）：
- 数据处理链路（平台分析、跨平台综合）优先走 `SiliconFlow`
- 总结链路（低成本摘要、主张文本总结）优先走 `DashScope`

### 2. 启动服务

运行启动脚本，它会自动启动前后端服务：

```bash
./scripts/start-dev.sh
```

这个脚本会：
1. 检查系统依赖（Node.js, Python, npm）
2. 验证环境配置文件
3. 安装项目依赖（如果需要）
4. 启动后端服务（端口 8000）
5. 等待后端就绪
6. 启动前端服务（端口 5173）
7. 显示访问地址和进程信息

### 3. 访问应用

服务启动成功后，您可以访问：

- **前端应用**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### 4. 停止服务

当您完成开发工作后，运行停止脚本：

```bash
./scripts/stop-dev.sh
```

这个脚本会：
- 优雅停止前后端进程
- 清理PID文件
- 保留日志文件供查看

### 5. 最小 Smoke 验证（5分钟）

按下面顺序执行，可快速确认“run + stream + report”链路可用：

```bash
# 1) 启动
./scripts/start-dev.sh

# 2) 健康检查
curl -s http://localhost:8000/health

# 3) 发起核验任务
curl -s -X POST http://localhost:8000/api/v1/investigations/run \
  -H 'Content-Type: application/json' \
  -d '{"claim":"example domain","keyword":"example domain","platforms":["bbc","reuters","xinhua"],"source_strategy":"auto"}'

# 4) 浏览器打开前端，观察 SSE 树状流程与报告页
# http://localhost:5173
```

快速定位路径：
- 后端日志：`runtime/logs/backend.log`
- 前端日志：`runtime/logs/frontend.log`
- 浏览器控制台：Network / Console（检查 SSE 与 API 失败）

### 6. 分阶段质量验收（推荐）

不要把“流程跑通”当作通过标准。建议使用阶段质量门脚本，逐阶段核验：
- `health_check`
- `preview_quality`
- `run_acceptance`
- `stream_quality`
- `result_quality`

执行示例：

```bash
cd aletheia-backend
python3 scripts/stage_quality_gate.py \
  --claim "OpenAI发布了新的模型能力更新" \
  --keyword "OpenAI 模型更新" \
  --max-attempts 2
```

你可以按场景调节阈值，例如：
- `--preview-summary-min-chars`
- `--stream-events-min`
- `--result-valid-evidence-min`
- `--result-platforms-with-data-min`
- `--result-duration-budget-sec`

验收输出包含每阶段：
- `expected`（预期）
- `observed`（实际）
- `issues`（不达标原因）
- `score`（阶段评分）

原则：任何阶段不达标，都先修阶段问题，再继续下一轮验收。

## 🔍 验证集成

### 方法1: 使用API连通性测试

运行自动化测试脚本验证所有关键端点：

```bash
node scripts/test-api-connectivity.ts
```

这个测试会验证：
- ✅ 健康检查端点
- ✅ 增强分析API
- ✅ 历史记录搜索API
- ✅ 多平台搜索API
- ✅ Playwright编排API

### 方法2: 使用API端点验证工具

验证前端API客户端与后端路由的匹配性：

```bash
node scripts/verify-api-endpoints.ts
```

这个工具会：
- 提取前端API调用
- 提取后端路由定义
- 比对并生成差异报告

### 方法3: 手动测试

1. 打开浏览器访问 http://localhost:5173
2. 打开浏览器开发者工具（F12）
3. 在前端界面进行操作
4. 检查Network标签，确认API请求成功
5. 检查Console标签，确认没有CORS错误

## 📝 开发工作流

### 查看日志

前后端日志文件位于项目根目录：

```bash
# 查看后端日志
tail -f runtime/logs/backend.log

# 查看前端日志
tail -f runtime/logs/frontend.log
```

### 热重载

- **前端**: Vite自动热重载，修改代码后浏览器自动刷新
- **后端**: Uvicorn自动重载，修改代码后服务自动重启

### 调试

#### 前端调试
- 使用浏览器开发者工具
- 在代码中添加 `console.log()` 或 `debugger`
- 使用React DevTools扩展

#### 后端调试
- 查看 `runtime/logs/backend.log` 日志文件
- 在代码中添加 `logger.info()` 或 `logger.error()`
- 使用Python调试器（pdb）

## 🔧 常见配置

### 修改端口

#### 前端端口（默认5173）

编辑 `frontend/vite.config.ts`:

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // 修改为您想要的端口
  },
})
```

记得同时更新后端CORS配置！

#### 后端端口（默认8000）

编辑 `scripts/start-dev.sh`，修改uvicorn命令：

```bash
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 9000
```

记得同时更新前端API_BASE_URL配置！

### 添加环境变量

#### 前端

在 `frontend/.env` 中添加：

```env
VITE_YOUR_VARIABLE=value
```

在代码中使用：

```typescript
const value = import.meta.env.VITE_YOUR_VARIABLE
```

#### 后端

在 `aletheia-backend/.env` 中添加：

```env
YOUR_VARIABLE=value
```

在 `core/config.py` 中定义：

```python
class Settings(BaseSettings):
    YOUR_VARIABLE: str
```

在代码中使用：

```python
from core.config import settings
value = settings.YOUR_VARIABLE
```

## 📊 API端点列表

### 核心端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/intel/enhanced/analyze/enhanced` | POST | 增强分析 |
| `/api/v1/intel/enhanced/search` | POST | 历史记录搜索 |
| `/api/v1/intel/enhanced/{intel_id}` | GET | 获取报告详情 |
| `/api/v1/multiplatform/search` | POST | 多平台搜索 |
| `/api/v1/multiplatform/aggregate` | POST | 多平台聚合 |
| `/api/v1/multiplatform/multi-agent-analyze` | POST | 多Agent分析 |
| `/api/v1/multiplatform/playwright-orchestrate` | POST | Playwright编排 |

### API文档

完整的API文档可以在以下地址查看：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🎯 下一步

现在您已经成功集成了前后端，可以：

1. 探索前端界面功能
2. 查看API文档了解更多端点
3. 阅读 `TROUBLESHOOTING.md` 了解常见问题
4. 开始开发新功能

## 📚 相关文档

- [故障排除指南](TROUBLESHOOTING.md)
- [后端README](aletheia-backend/README.md)
- [前端README](frontend/README.md)
- [API设计文档](.kiro/specs/backend-frontend-integration/design.md)

## 💡 提示

- 首次启动可能需要较长时间安装依赖
- 确保端口8000和5173未被占用
- 如遇到问题，先查看日志文件
- 使用 `./scripts/stop-dev.sh` 停止服务，不要直接关闭终端

---

**祝您开发愉快！** 🚀
