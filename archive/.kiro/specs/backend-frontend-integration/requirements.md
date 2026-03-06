# Requirements Document

## Introduction

本文档定义了将Aletheia后端API集成到前端React应用的需求。项目包含一个FastAPI后端（运行在http://localhost:8000）和一个React+Vite+TypeScript前端（运行在http://localhost:5173）。前端已有API客户端代码（frontend/src/api.ts），需要确保后端API与前端客户端完全匹配，并提供完整的集成验证和启动流程。

## Glossary

- **Backend**: FastAPI应用，位于aletheia-backend/目录，提供RESTful API服务
- **Frontend**: React+Vite+TypeScript应用，位于frontend/目录，消费后端API
- **API_Client**: 前端API客户端模块（frontend/src/api.ts），封装所有后端API调用
- **CORS**: 跨域资源共享机制，允许前端从不同端口访问后端API
- **Environment_Config**: 环境变量配置文件（.env），存储API端点和凭证信息
- **API_Endpoint**: 后端提供的HTTP端点，前缀为/api/v1
- **Integration_Test**: 验证前后端连通性和数据交互的测试脚本

## Requirements

### Requirement 1: API端点验证

**User Story:** 作为开发者，我希望验证后端API端点与前端API客户端的匹配性，以确保所有前端调用都能正确路由到后端。

#### Acceptance Criteria

1. WHEN 前端API客户端调用任何端点 THEN THE Backend SHALL 提供对应的路由处理器
2. WHEN 检查API路由定义 THEN THE System SHALL 列出所有后端已实现的端点及其HTTP方法
3. WHEN 比对前端API调用 THEN THE System SHALL 标识出前端使用但后端未实现的端点
4. WHEN 发现端点不匹配 THEN THE System SHALL 生成详细的差异报告
5. THE Verification_Script SHALL 自动化执行端点匹配检查

### Requirement 2: CORS配置验证

**User Story:** 作为开发者，我希望确保CORS配置正确，以便前端（端口5173）能够成功访问后端（端口8000）。

#### Acceptance Criteria

1. WHEN 后端启动时 THEN THE Backend SHALL 在CORS允许源列表中包含http://localhost:5173
2. WHEN 前端发起跨域请求 THEN THE Backend SHALL 返回正确的CORS响应头
3. WHEN 前端发起预检请求（OPTIONS） THEN THE Backend SHALL 正确响应并允许后续请求
4. THE Backend SHALL 允许所有必要的HTTP方法（GET、POST、PUT、DELETE、OPTIONS）
5. THE Backend SHALL 允许所有必要的请求头（Content-Type、Authorization等）

### Requirement 3: 环境变量配置

**User Story:** 作为开发者，我希望创建和配置环境变量文件，以便前后端能够使用正确的配置参数。

#### Acceptance Criteria

1. WHEN 前端项目缺少.env文件 THEN THE System SHALL 从.env.example创建.env文件
2. WHEN 后端项目缺少.env文件 THEN THE System SHALL 从.env.example创建.env文件并填充必要的默认值
3. THE Frontend_Env SHALL 包含VITE_API_BASE_URL指向http://localhost:8000/api/v1
4. THE Backend_Env SHALL 包含BACKEND_CORS_ORIGINS包括前端端口5173
5. WHEN 环境变量缺失关键配置 THEN THE System SHALL 提供清晰的错误提示和配置指南

### Requirement 4: API连通性测试

**User Story:** 作为开发者，我希望测试关键API端点的连通性，以验证前后端能够正常通信。

#### Acceptance Criteria

1. WHEN 执行连通性测试 THEN THE Test_Script SHALL 验证后端健康检查端点（/health）可访问
2. WHEN 测试增强分析API THEN THE Test_Script SHALL 发送示例请求到/api/v1/intel/enhanced/analyze/enhanced并验证响应格式
3. WHEN 测试多平台搜索API THEN THE Test_Script SHALL 发送请求到/api/v1/multiplatform/search并验证响应
4. WHEN 测试历史记录API THEN THE Test_Script SHALL 发送请求到/api/v1/intel/enhanced/search并验证分页响应
5. WHEN 任何测试失败 THEN THE Test_Script SHALL 提供详细的错误信息和调试建议
6. THE Test_Script SHALL 生成测试报告，包含所有端点的测试结果

### Requirement 5: 启动脚本优化

**User Story:** 作为开发者，我希望有统一的启动脚本，能够正确启动前后端服务并验证它们的协同工作。

#### Acceptance Criteria

1. WHEN 执行启动脚本 THEN THE Script SHALL 首先检查所有必要的依赖是否已安装
2. WHEN 启动后端 THEN THE Script SHALL 在后台启动FastAPI服务器并验证其健康状态
3. WHEN 启动前端 THEN THE Script SHALL 在后台启动Vite开发服务器并验证其可访问性
4. WHEN 服务启动失败 THEN THE Script SHALL 提供清晰的错误信息和解决建议
5. THE Script SHALL 提供停止所有服务的功能
6. THE Script SHALL 在启动完成后显示访问URL和下一步操作指南

### Requirement 6: 集成文档

**User Story:** 作为开发者，我希望有完整的集成文档，说明如何配置、启动和测试前后端集成。

#### Acceptance Criteria

1. THE Documentation SHALL 包含前置条件检查清单（Node.js、Python、依赖包等）
2. THE Documentation SHALL 提供分步骤的环境配置指南
3. THE Documentation SHALL 说明如何启动和停止前后端服务
4. THE Documentation SHALL 包含常见问题和故障排除指南
5. THE Documentation SHALL 提供API端点使用示例
6. THE Documentation SHALL 说明如何验证集成是否成功

### Requirement 7: 错误处理和日志

**User Story:** 作为开发者，我希望前后端都有清晰的错误处理和日志记录，以便快速定位和解决问题。

#### Acceptance Criteria

1. WHEN 前端API调用失败 THEN THE API_Client SHALL 提供包含错误详情和后端URL的错误消息
2. WHEN 后端处理请求失败 THEN THE Backend SHALL 返回结构化的错误响应（包含error和detail字段）
3. WHEN 网络连接失败 THEN THE Frontend SHALL 提示用户检查后端是否已启动
4. THE Backend SHALL 记录所有API请求和响应的日志，包含时间戳、端点、状态码和耗时
5. THE Frontend SHALL 在开发模式下将API错误输出到浏览器控制台

### Requirement 8: 数据格式一致性

**User Story:** 作为开发者，我希望确保前后端的数据类型定义一致，避免类型不匹配导致的运行时错误。

#### Acceptance Criteria

1. WHEN 后端返回分析结果 THEN THE Response SHALL 匹配前端AnalyzeResponse接口定义
2. WHEN 后端返回历史记录 THEN THE Response SHALL 匹配前端HistoryListResponse接口定义
3. WHEN 后端返回Intel对象 THEN THE Response SHALL 包含前端IntelData接口定义的所有必需字段
4. THE System SHALL 提供类型验证脚本，检查前后端类型定义的一致性
5. WHEN 发现类型不匹配 THEN THE Validation_Script SHALL 生成详细的差异报告

### Requirement 9: 开发工作流集成

**User Story:** 作为开发者，我希望开发工作流能够支持热重载和快速迭代，提高开发效率。

#### Acceptance Criteria

1. WHEN 修改后端代码 THEN THE Backend SHALL 自动重启并保持前端连接
2. WHEN 修改前端代码 THEN THE Frontend SHALL 热重载而不影响后端
3. THE Development_Script SHALL 同时监控前后端进程的健康状态
4. WHEN 任一服务崩溃 THEN THE Script SHALL 发出警告并提供重启选项
5. THE Script SHALL 提供查看前后端日志的便捷方式
