# Design Document: Backend-Frontend Integration

## Overview

本设计文档描述了将Aletheia后端API（FastAPI）与前端应用（React+Vite+TypeScript）集成的技术方案。集成的核心目标是确保前后端能够无缝通信，包括API端点匹配、CORS配置、环境变量管理、连通性测试和开发工作流优化。

### 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     开发者工作流                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 环境配置脚本  │  │ 启动脚本      │  │ 测试脚本      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌───────▼────────┐  ┌──────▼──────┐
│  前端应用       │  │  后端API        │  │  验证工具    │
│  (React+Vite)  │  │  (FastAPI)     │  │             │
│  Port: 5173    │  │  Port: 8000    │  │  - 端点验证  │
│                │  │                │  │  - 类型检查  │
│  ┌──────────┐  │  │  ┌──────────┐  │  │  - 连通测试  │
│  │ API客户端 │◄─┼──┼─►│ API路由  │  │  └─────────────┘
│  │ (api.ts) │  │  │  │ (/api/v1)│  │
│  └──────────┘  │  │  └──────────┘  │
│                │  │                │
│  ┌──────────┐  │  │  ┌──────────┐  │
│  │ 环境配置  │  │  │  │ CORS配置 │  │
│  │ (.env)   │  │  │  │ (config) │  │
│  └──────────┘  │  │  └──────────┘  │
└────────────────┘  └────────────────┘
```

### 技术栈

**前端:**
- React 18
- Vite 5
- TypeScript 5
- 运行端口: 5173

**后端:**
- FastAPI
- Python 3.10+
- Uvicorn
- 运行端口: 8000
- API前缀: /api/v1

## Architecture

### 组件交互流程

1. **开发者启动流程**
   - 执行环境配置脚本 → 创建/验证.env文件
   - 执行启动脚本 → 启动后端和前端服务
   - 执行测试脚本 → 验证集成是否成功

2. **前端API调用流程**
   - 前端组件调用API客户端方法
   - API客户端构造HTTP请求（添加base URL和headers）
   - 浏览器发送请求到后端（可能触发CORS预检）
   - 后端处理请求并返回响应
   - API客户端解析响应或处理错误
   - 前端组件接收数据或错误信息

3. **CORS处理流程**
   - 浏览器检测跨域请求
   - 发送OPTIONS预检请求（对于非简单请求）
   - 后端返回CORS响应头
   - 浏览器验证CORS头并允许/拒绝实际请求

## Components and Interfaces

### 1. API端点验证工具 (scripts/verify-api-endpoints.ts)

**职责:** 验证前端API客户端调用的所有端点在后端都有对应实现

**输入:**
- 前端API客户端代码 (frontend/src/api.ts)
- 后端路由定义 (aletheia-backend/api/v1/)

**输出:**
- 端点匹配报告
- 不匹配端点列表
- HTTP方法验证结果

**核心算法:**
```typescript
interface EndpointInfo {
  path: string;
  method: string;
  source: 'frontend' | 'backend';
}

function extractFrontendEndpoints(apiClientCode: string): EndpointInfo[] {
  // 解析api.ts中的fetch调用
  // 提取路径和HTTP方法
}

function extractBackendEndpoints(routerFiles: string[]): EndpointInfo[] {
  // 解析FastAPI路由装饰器
  // 提取@router.get/@router.post等
}

function compareEndpoints(
  frontendEndpoints: EndpointInfo[],
  backendEndpoints: EndpointInfo[]
): {
  matched: EndpointInfo[];
  missingInBackend: EndpointInfo[];
  unusedInFrontend: EndpointInfo[];
} {
  // 比对逻辑
}
```

### 2. 环境配置管理器 (scripts/setup-env.sh)

**职责:** 创建和验证前后端环境变量配置

**功能:**
- 检查.env文件是否存在
- 从.env.example复制并填充默认值
- 验证必需配置项
- 提供配置指南

**配置项映射:**

前端 (.env):
```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

后端 (.env):
```bash
# API配置
API_HOST=0.0.0.0
API_PORT=8000

# CORS配置
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://127.0.0.1:5173"]

# 必需的LLM配置（至少一个）
SILICONFLOW_API_KEY=your_key_here
# 或
KIMI_API_KEY=your_key_here
```

### 3. API连通性测试套件 (scripts/test-api-connectivity.ts)

**职责:** 测试关键API端点的连通性和响应格式

**测试端点列表:**
1. `/health` - 健康检查
2. `/api/v1/intel/enhanced/analyze/enhanced` - 增强分析
3. `/api/v1/multiplatform/search` - 多平台搜索
4. `/api/v1/intel/enhanced/search` - 历史记录搜索
5. `/api/v1/multiplatform/playwright-orchestrate` - Playwright编排

**测试用例结构:**
```typescript
interface TestCase {
  name: string;
  endpoint: string;
  method: 'GET' | 'POST';
  payload?: any;
  expectedStatus: number;
  validateResponse: (response: any) => boolean;
}

const testCases: TestCase[] = [
  {
    name: '健康检查',
    endpoint: '/health',
    method: 'GET',
    expectedStatus: 200,
    validateResponse: (res) => res.status === 'healthy'
  },
  {
    name: '增强分析API',
    endpoint: '/api/v1/intel/enhanced/analyze/enhanced',
    method: 'POST',
    payload: {
      content: '测试内容',
      source_platform: 'web'
    },
    expectedStatus: 200,
    validateResponse: (res) => 
      res.intel && res.reasoning_chain && res.processing_time_ms
  }
  // ... 更多测试用例
];
```

### 4. 统一启动脚本 (scripts/start-dev.sh)

**职责:** 启动前后端服务并监控健康状态

**流程:**
```bash
#!/bin/bash

# 1. 检查依赖
check_dependencies() {
  command -v node >/dev/null 2>&1 || { echo "需要Node.js"; exit 1; }
  command -v python3 >/dev/null 2>&1 || { echo "需要Python3"; exit 1; }
}

# 2. 检查环境配置
check_env_files() {
  [ -f frontend/.env ] || { echo "缺少前端.env"; exit 1; }
  [ -f aletheia-backend/.env ] || { echo "缺少后端.env"; exit 1; }
}

# 3. 启动后端
start_backend() {
  cd aletheia-backend
  python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
  BACKEND_PID=$!
  echo "后端PID: $BACKEND_PID"
}

# 4. 等待后端就绪
wait_for_backend() {
  for i in {1..30}; do
    curl -s http://localhost:8000/health && break
    sleep 1
  done
}

# 5. 启动前端
start_frontend() {
  cd frontend
  npm run dev &
  FRONTEND_PID=$!
  echo "前端PID: $FRONTEND_PID"
}

# 6. 监控进程
monitor_processes() {
  while true; do
    kill -0 $BACKEND_PID 2>/dev/null || { echo "后端崩溃"; exit 1; }
    kill -0 $FRONTEND_PID 2>/dev/null || { echo "前端崩溃"; exit 1; }
    sleep 5
  done
}
```

### 5. 类型一致性验证器 (scripts/validate-types.ts)

**职责:** 验证前后端数据类型定义的一致性

**验证策略:**
- 提取前端TypeScript接口定义
- 提取后端Pydantic模型定义
- 比对字段名称、类型和必需性
- 生成差异报告

**关键类型映射:**

前端 (TypeScript):
```typescript
export interface AnalyzeResponse {
  intel: IntelData;
  reasoning_chain: ReasoningChain;
  processing_time_ms: number;
}

export interface IntelData {
  id: string;
  content_text: string;
  source_platform?: string;
  credibility_score?: number;
  credibility_level?: string;
  // ...
}
```

后端 (Python):
```python
class EnhancedIntelAnalyzeResponse(BaseModel):
    intel: dict
    reasoning_chain: ReasoningChainResponse
    processing_time_ms: int

class IntelData(BaseModel):
    id: str
    content_text: str
    source_platform: Optional[str]
    credibility_score: Optional[float]
    credibility_level: Optional[str]
    # ...
```

## Data Models

### API端点映射表

| 前端API方法 | HTTP方法 | 后端端点 | 状态 |
|------------|---------|---------|------|
| analyzeEnhanced | POST | /api/v1/intel/enhanced/analyze/enhanced | ✅ 已实现 |
| searchMultiplatform | POST | /api/v1/multiplatform/search | ✅ 已实现 |
| aggregateMultiplatform | POST | /api/v1/multiplatform/aggregate | ✅ 已实现 |
| multiAgentAnalyze | POST | /api/v1/multiplatform/multi-agent-analyze | ✅ 已实现 |
| fetchAnalysisHistory | POST | /api/v1/intel/enhanced/search | ✅ 已实现 |
| fetchEnhancedById | GET | /api/v1/intel/enhanced/{intel_id} | ✅ 已实现 |

### CORS配置模型

```python
# aletheia-backend/core/config.py
class Settings(BaseSettings):
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
```

```python
# aletheia-backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 错误响应模型

统一错误响应格式:
```typescript
interface ErrorResponse {
  error: string;        // 错误类型
  detail: string;       // 详细信息
  status_code?: number; // HTTP状态码
}
```

前端错误处理:
```typescript
async function requestJson<T>(
  path: string,
  init: RequestInit,
  fallbackMessage: string
): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    
    if (!response.ok) {
      let detail = '';
      try {
        const payload = await response.json();
        detail = payload?.detail || payload?.message || '';
      } catch {
        detail = await response.text();
      }
      throw new Error(detail || fallbackMessage);
    }
    
    return response.json();
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'unknown error';
    throw new Error(`网络请求失败（${msg}）。请确认后端已启动：${API_BASE}`);
  }
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 端点完整性

*For any* API调用在前端API客户端中定义，后端应该有对应的路由处理器，并且HTTP方法匹配。

**Validates: Requirements 1.1, 1.3, 1.4**

### Property 2: CORS响应正确性

*For any* 从前端端口5173发起的HTTP请求，后端应该返回包含正确CORS头的响应，允许该请求通过。

**Validates: Requirements 2.2, 2.3**

### Property 3: 错误处理一致性

*For any* 系统组件（配置脚本、测试脚本、启动脚本）遇到错误时，应该提供包含错误详情和解决建议的清晰错误消息。

**Validates: Requirements 3.5, 4.5, 5.4, 9.4**

### Property 4: 错误响应格式统一性

*For any* API请求失败，后端应该返回包含error和detail字段的结构化JSON响应，前端应该将其转换为包含后端URL的用户友好错误消息。

**Validates: Requirements 7.1, 7.2**

### Property 5: 响应类型一致性

*For any* 后端API响应，其数据结构应该与前端TypeScript接口定义完全匹配，包括字段名称、类型和必需性。

**Validates: Requirements 8.1, 8.2, 8.3, 8.5**

### Property 6: 日志完整性

*For any* 后端API请求，应该记录包含时间戳、HTTP方法、端点路径、状态码和处理耗时的日志条目。

**Validates: Requirements 7.4**

## Error Handling

### 错误分类和处理策略

**1. 网络连接错误**
- 场景: 后端未启动或网络不可达
- 前端处理: 捕获fetch异常，提示"请确认后端已启动"
- 用户操作: 检查后端服务状态

**2. CORS错误**
- 场景: CORS配置不正确
- 表现: 浏览器控制台显示CORS错误
- 解决: 验证后端CORS配置包含前端端口

**3. API端点不存在 (404)**
- 场景: 前端调用了后端未实现的端点
- 后端响应: 404 Not Found
- 前端处理: 显示"API端点不存在"错误
- 开发者操作: 运行端点验证脚本

**4. 请求参数错误 (400/422)**
- 场景: 请求payload不符合后端schema
- 后端响应: 422 Unprocessable Entity with validation details
- 前端处理: 显示验证错误详情
- 开发者操作: 检查类型定义一致性

**5. 服务器内部错误 (500)**
- 场景: 后端处理逻辑异常
- 后端响应: 500 Internal Server Error
- 后端日志: 记录完整异常堆栈
- 前端处理: 显示通用错误消息（生产环境）或详细错误（开发环境）

**6. 环境配置错误**
- 场景: 缺少必需的环境变量
- 检测时机: 服务启动时
- 处理: 启动失败并显示缺失的配置项
- 解决: 运行环境配置脚本

### 错误恢复机制

**前端重试策略:**
- 网络错误: 不自动重试，提示用户手动重试
- 5xx错误: 可选择性重试（用户触发）
- 4xx错误: 不重试，显示错误信息

**后端容错:**
- 数据库连接失败: 降级到内存存储
- Redis不可用: 禁用缓存功能但继续服务
- LLM API失败: 返回降级响应或错误

## Testing Strategy

### 测试方法论

本项目采用**双重测试策略**：
- **单元测试**: 验证具体示例、边缘情况和错误条件
- **属性测试**: 验证跨所有输入的通用属性

两者互补，共同确保全面覆盖。

### 单元测试

单元测试专注于：
- 具体示例（如特定端点的调用）
- 组件间集成点
- 边缘情况和错误条件

**不要编写过多单元测试** - 属性测试已经处理了大量输入覆盖。

**测试工具:**
- 前端: Vitest
- 后端: pytest
- 集成: Shell脚本 + curl

**关键单元测试:**

1. **端点验证脚本测试**
   - 测试脚本能正确解析前端API调用
   - 测试脚本能正确解析后端路由定义
   - 测试报告生成功能

2. **环境配置脚本测试**
   - 测试.env文件创建
   - 测试默认值填充
   - 测试配置验证逻辑

3. **连通性测试脚本测试**
   - 测试健康检查端点
   - 测试各个API端点的基本调用
   - 测试响应格式验证

4. **启动脚本测试**
   - 测试依赖检查
   - 测试服务启动逻辑
   - 测试进程监控

### 属性测试

属性测试验证跨所有输入的通用属性。

**配置要求:**
- 每个属性测试最少运行100次迭代
- 使用fast-check (TypeScript) 或 Hypothesis (Python)
- 每个测试必须引用设计文档中的属性

**标签格式:**
```typescript
// Feature: backend-frontend-integration, Property 1: 端点完整性
```

**关键属性测试:**

1. **Property 1: 端点完整性测试**
   ```typescript
   // Feature: backend-frontend-integration, Property 1: 端点完整性
   fc.assert(
     fc.property(
       fc.array(endpointGenerator),
       (frontendEndpoints) => {
         const backendEndpoints = extractBackendEndpoints();
         const missing = findMissingEndpoints(frontendEndpoints, backendEndpoints);
         return missing.length === 0;
       }
     ),
     { numRuns: 100 }
   );
   ```

2. **Property 2: CORS响应正确性测试**
   ```typescript
   // Feature: backend-frontend-integration, Property 2: CORS响应正确性
   fc.assert(
     fc.property(
       fc.constantFrom('GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'),
       fc.oneof(fc.constant('/api/v1/health'), fc.constant('/api/v1/intel/enhanced/search')),
       async (method, path) => {
         const response = await fetch(`http://localhost:8000${path}`, {
           method,
           headers: { 'Origin': 'http://localhost:5173' }
         });
         const corsHeader = response.headers.get('Access-Control-Allow-Origin');
         return corsHeader === 'http://localhost:5173' || corsHeader === '*';
       }
     ),
     { numRuns: 100 }
   );
   ```

3. **Property 5: 响应类型一致性测试**
   ```typescript
   // Feature: backend-frontend-integration, Property 5: 响应类型一致性
   fc.assert(
     fc.property(
       analyzeRequestGenerator,
       async (request) => {
         const response = await analyzeEnhanced(request);
         return (
           typeof response.intel === 'object' &&
           typeof response.reasoning_chain === 'object' &&
           typeof response.processing_time_ms === 'number' &&
           Array.isArray(response.reasoning_chain.steps)
         );
       }
     ),
     { numRuns: 100 }
   );
   ```

### 集成测试

**端到端流程测试:**
1. 启动后端和前端
2. 执行完整的用户流程（提交分析 → 查看结果 → 查看历史）
3. 验证数据流转正确性

**测试环境:**
- 使用Docker Compose启动隔离环境
- 使用测试数据库和测试API密钥
- 自动化清理测试数据

### 测试执行顺序

1. **开发阶段**: 运行单元测试（快速反馈）
2. **提交前**: 运行属性测试（全面验证）
3. **CI/CD**: 运行所有测试 + 集成测试

### 测试覆盖率目标

- 脚本代码: 80%+
- API客户端: 90%+
- 关键路径: 100%

## Implementation Notes

### 开发优先级

1. **Phase 1: 基础设施** (高优先级)
   - 环境配置脚本
   - 端点验证工具
   - 基础连通性测试

2. **Phase 2: 开发体验** (中优先级)
   - 统一启动脚本
   - 进程监控
   - 日志聚合

3. **Phase 3: 质量保证** (中优先级)
   - 类型一致性验证
   - 属性测试
   - 集成文档

4. **Phase 4: 优化** (低优先级)
   - 性能监控
   - 错误追踪
   - 自动化部署

### 技术决策

**为什么选择Shell脚本而不是Node.js脚本？**
- Shell脚本更适合系统级操作（进程管理、文件操作）
- 更容易在CI/CD环境中运行
- 减少依赖（不需要额外的Node包）

**为什么不使用Docker Compose进行开发？**
- 开发阶段需要热重载，Docker会增加复杂性
- 本地开发更快的迭代速度
- Docker Compose保留用于生产部署和集成测试

**为什么使用TypeScript编写验证工具？**
- 可以直接解析TypeScript接口定义
- 与前端代码库共享类型定义
- 更好的IDE支持

### 依赖管理

**前端依赖:**
```json
{
  "devDependencies": {
    "fast-check": "^3.15.0",
    "vitest": "^1.0.0"
  }
}
```

**后端依赖:**
```txt
# 已有依赖，无需额外添加
fastapi
uvicorn
pydantic
```

**系统依赖:**
- Node.js 18+
- Python 3.10+
- curl (用于健康检查)
- jq (用于JSON处理)

### 配置文件位置

```
project-root/
├── frontend/
│   ├── .env                    # 前端环境变量
│   ├── .env.example            # 前端环境变量模板
│   └── src/
│       └── api.ts              # API客户端
├── aletheia-backend/
│   ├── .env                    # 后端环境变量
│   ├── .env.example            # 后端环境变量模板
│   ├── main.py                 # 后端入口
│   └── core/
│       └── config.py           # 配置管理
└── scripts/
    ├── setup-env.sh            # 环境配置脚本
    ├── start-dev.sh            # 启动脚本
    ├── stop-dev.sh             # 停止脚本
    ├── verify-api-endpoints.ts # 端点验证
    ├── test-api-connectivity.ts# 连通性测试
    └── validate-types.ts       # 类型验证
```

### 日志策略

**后端日志:**
- 格式: JSON (便于解析)
- 级别: INFO (开发), WARNING (生产)
- 输出: 控制台 + 文件 (logs/aletheia.log)
- 包含: 请求ID、时间戳、端点、耗时、状态码

**前端日志:**
- 开发模式: console.log/error
- 生产模式: 发送到后端日志收集端点
- 包含: 用户操作、API调用、错误堆栈

### 性能考虑

**API响应时间目标:**
- 健康检查: < 50ms
- 简单查询: < 200ms
- 复杂分析: < 5s
- 批量操作: < 10s

**前端性能:**
- 首次加载: < 2s
- 路由切换: < 100ms
- API调用反馈: 立即显示加载状态

**优化策略:**
- 后端: 使用Redis缓存频繁查询
- 前端: 使用React Query缓存API响应
- 网络: 启用Gzip压缩
