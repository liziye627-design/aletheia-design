# Implementation Plan: Backend-Frontend Integration

## Overview

本实施计划将Aletheia后端API与前端应用集成，包括环境配置、API端点验证、连通性测试、启动脚本和开发工作流优化。采用多语言方案：TypeScript用于前端工具、Python用于后端、Shell用于系统脚本。

## Tasks

- [x] 1. 创建环境配置脚本
  - [x] 1.1 实现环境配置Shell脚本 (scripts/setup-env.sh)
    - 检查前后端.env文件是否存在
    - 从.env.example复制并创建.env文件
    - 验证必需配置项（VITE_API_BASE_URL、BACKEND_CORS_ORIGINS）
    - 提供缺失配置的清晰提示
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [ ]* 1.2 编写环境配置脚本的单元测试
    - 测试.env文件创建逻辑
    - 测试配置验证逻辑
    - 测试错误提示功能
    - _Requirements: 3.1, 3.2_

- [x] 2. 实现API端点验证工具
  - [x] 2.1 创建端点提取模块 (scripts/verify-api-endpoints.ts)
    - 实现前端API调用提取函数（解析api.ts中的fetch调用）
    - 实现后端路由提取函数（解析FastAPI装饰器）
    - 定义EndpointInfo接口和数据结构
    - _Requirements: 1.2_
  
  - [x] 2.2 实现端点比对逻辑
    - 实现compareEndpoints函数
    - 识别匹配、缺失和未使用的端点
    - 生成详细的差异报告
    - _Requirements: 1.3, 1.4_
  
  - [ ]* 2.3 编写端点验证工具的属性测试
    - **Property 1: 端点完整性**
    - **Validates: Requirements 1.1, 1.3, 1.4**
    - 测试所有前端端点在后端都有对应实现
    - 使用fast-check生成随机端点集合
    - 验证HTTP方法匹配

- [x] 3. Checkpoint - 验证基础工具
  - 确保环境配置脚本和端点验证工具正常工作，询问用户是否有问题

- [x] 4. 实现API连通性测试套件
  - [x] 4.1 创建测试框架 (scripts/test-api-connectivity.ts)
    - 定义TestCase接口
    - 实现测试执行引擎
    - 实现响应验证逻辑
    - _Requirements: 4.1, 4.6_
  
  - [x] 4.2 添加关键端点测试用例
    - 健康检查端点 (/health)
    - 增强分析API (/api/v1/intel/enhanced/analyze/enhanced)
    - 多平台搜索API (/api/v1/multiplatform/search)
    - 历史记录API (/api/v1/intel/enhanced/search)
    - Playwright编排API (/api/v1/multiplatform/playwright-orchestrate)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  
  - [x] 4.3 实现测试报告生成
    - 生成包含所有测试结果的报告
    - 对失败测试提供详细错误信息和调试建议
    - _Requirements: 4.5, 4.6_
  
  - [ ]* 4.4 编写连通性测试的单元测试
    - 测试测试框架本身
    - 测试响应验证逻辑
    - 测试报告生成功能
    - _Requirements: 4.1, 4.6_

- [x] 5. 验证和增强CORS配置
  - [x] 5.1 验证后端CORS配置
    - 检查core/config.py中的BACKEND_CORS_ORIGINS
    - 确保包含http://localhost:5173和http://127.0.0.1:5173
    - 验证main.py中的CORSMiddleware配置
    - _Requirements: 2.1, 2.4, 2.5_
  
  - [ ]* 5.2 编写CORS配置的属性测试
    - **Property 2: CORS响应正确性**
    - **Validates: Requirements 2.2, 2.3**
    - 测试各种HTTP方法的CORS响应
    - 测试OPTIONS预检请求
    - 验证CORS响应头正确性

- [x] 6. 创建统一启动脚本
  - [x] 6.1 实现启动脚本 (scripts/start-dev.sh)
    - 实现依赖检查（Node.js、Python、npm、pip）
    - 实现环境配置检查
    - 实现后端启动逻辑（uvicorn）
    - 实现前端启动逻辑（npm run dev）
    - 实现健康检查等待逻辑
    - _Requirements: 5.1, 5.2, 5.3_
  
  - [x] 6.2 实现进程监控和错误处理
    - 监控前后端进程健康状态
    - 捕获启动失败并提供错误信息
    - 显示访问URL和操作指南
    - _Requirements: 5.4, 5.6_
  
  - [x] 6.3 实现停止脚本 (scripts/stop-dev.sh)
    - 优雅停止前后端进程
    - 清理临时文件和PID文件
    - _Requirements: 5.5_
  
  - [ ]* 6.4 编写启动脚本的集成测试
    - 测试完整启动流程
    - 测试错误处理逻辑
    - 测试停止功能
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 7. Checkpoint - 验证启动流程
  - 确保启动脚本能正确启动前后端服务，询问用户是否有问题

- [x] 8. 实现类型一致性验证工具
  - [x] 8.1 创建类型提取模块 (scripts/validate-types.ts)
    - 实现TypeScript接口提取（解析前端类型定义）
    - 实现Python模型提取（解析Pydantic模型）
    - 定义类型映射规则（TypeScript ↔ Python）
    - _Requirements: 8.4_
  
  - [x] 8.2 实现类型比对逻辑
    - 比对字段名称、类型和必需性
    - 识别类型不匹配
    - 生成详细差异报告
    - _Requirements: 8.4, 8.5_
  
  - [ ]* 8.3 编写类型验证的属性测试
    - **Property 5: 响应类型一致性**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5**
    - 测试各种API响应的类型匹配
    - 使用fast-check生成随机请求
    - 验证响应结构完整性

- [x] 9. 增强错误处理和日志
  - [x] 9.1 验证前端错误处理
    - 检查api.ts中的错误处理逻辑
    - 确保网络错误提供后端URL提示
    - 确保API错误显示详细信息
    - _Requirements: 7.1, 7.3, 7.5_
  
  - [x] 9.2 验证后端错误处理
    - 检查main.py中的全局异常处理器
    - 确保错误响应包含error和detail字段
    - 验证日志记录包含所有必需信息
    - _Requirements: 7.2, 7.4_
  
  - [ ]* 9.3 编写错误处理的属性测试
    - **Property 3: 错误处理一致性**
    - **Validates: Requirements 3.5, 4.5, 5.4, 9.4**
    - 测试各种错误场景的处理
    - **Property 4: 错误响应格式统一性**
    - **Validates: Requirements 7.1, 7.2**
    - 测试错误响应格式
    - **Property 6: 日志完整性**
    - **Validates: Requirements 7.4**
    - 测试日志记录完整性

- [x] 10. 创建集成文档
  - [x] 10.1 编写INTEGRATION_GUIDE.md
    - 前置条件检查清单
    - 分步骤环境配置指南
    - 启动和停止服务说明
    - API端点使用示例
    - 集成验证步骤
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_
  
  - [x] 10.2 编写TROUBLESHOOTING.md
    - 常见问题列表
    - 故障排除步骤
    - 错误消息解释
    - 解决方案建议
    - _Requirements: 6.4_

- [x] 11. 实现开发工作流优化
  - [x] 11.1 配置后端热重载
    - 验证uvicorn --reload配置
    - 测试代码修改后的自动重启
    - _Requirements: 9.1_
  
  - [x] 11.2 配置前端热重载
    - 验证Vite HMR配置
    - 测试代码修改后的热更新
    - _Requirements: 9.2_
  
  - [x] 11.3 增强启动脚本的监控功能
    - 添加进程健康检查
    - 添加崩溃检测和警告
    - 添加日志查看功能
    - _Requirements: 9.3, 9.4, 9.5_

- [x] 12. 最终集成测试和验证
  - [x] 12.1 执行完整集成测试
    - 运行环境配置脚本
    - 运行启动脚本
    - 运行端点验证工具
    - 运行连通性测试
    - 运行类型验证工具
    - _Requirements: 所有需求_
  
  - [x] 12.2 验证所有正确性属性
    - 验证Property 1: 端点完整性
    - 验证Property 2: CORS响应正确性
    - 验证Property 3: 错误处理一致性
    - 验证Property 4: 错误响应格式统一性
    - 验证Property 5: 响应类型一致性
    - 验证Property 6: 日志完整性
  
  - [x] 12.3 执行端到端用户流程测试
    - 启动前后端服务
    - 在前端提交分析请求
    - 验证分析结果显示
    - 查看历史记录
    - 验证数据持久化

- [x] 13. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题

## Notes

- 标记为`*`的任务是可选的测试任务，可以跳过以加快MVP开发
- 每个任务都引用了具体的需求编号，确保可追溯性
- Checkpoint任务确保增量验证，及早发现问题
- 属性测试验证通用正确性属性，单元测试验证具体示例和边缘情况
- 多语言方案：TypeScript工具 + Python后端 + Shell脚本，充分利用各语言优势
