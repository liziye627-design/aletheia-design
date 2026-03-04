# Aletheia 真相洞察引擎 - 演示指南

## 🚀 系统已启动

- **前端地址**: http://localhost:5173
- **后端API**: http://localhost:8000 (需要Redis支持，演示使用Mock数据)

## 📝 GPT-5.3 演示案例

系统预置了一个关于 **"GPT-5.3模型发布"** 的虚假信息案例，用于演示完整的8步推理链分析。

### 虚假声明内容：
```
"OpenAI 宣布 GPT-5.3 模型正式发布，具备自我学习和代码重构能力，
可以自动修复bug并优化算法性能"
```

### 分析结果示例：
- **可信度**: 15% · VERY_LOW
- **风险等级**: 虚假信息 + 水军操作
- **推理步骤**: 8步完整推理链

## 🛠️ 三种工具模式

### 1. 双工模式 (Dual Mode)
- **功能**: 同时进行内容核验 + 多源检索
- **适用**: 快速验证 + 获取相关证据
- **API调用**: `dualModeAnalysis()`

### 2. 增强核验 (Enhanced Verification)
- **功能**: 完整的8步推理链深度分析
- **适用**: 复杂信息的事实核查
- **API调用**: `enhancedVerification()`

### 3. 多源检索 (Multi-Source Search)
- **功能**: 跨平台数据聚合与传播分析
- **适用**: 追踪话题趋势和舆论走向
- **API调用**: `multiSourceSearch()`

## 🎯 8步推理链

1. **预处理** - 提取核心主张和关键词
2. **物理层检验** - 时间/地点/物理规律一致性
3. **逻辑层检验** - 因果链完整性和逻辑谬误检测
4. **信源分析** - 账号画像和传播结构评分
5. **交叉验证** - 多源事实一致性比对
6. **异常检测** - Layer2检测协同传播信号
7. **证据综合** - 支持证据与疑点汇总
8. **自我反思** - 偏见校正并输出final_score

## 📊 演示数据

系统使用Mock数据展示以下场景：

### 案例特征：
- ❌ 虚假版本号 (GPT-5.3不存在)
- ❌ 夸大技术能力 (自我学习、自动重构)
- ❌ 可疑信源 (新注册账号)
- ❌ 水军操作 (23个账号协同转发)
- ❌ 无官方确认

### 分析指标：
```json
{
  "final_score": 0.15,
  "final_level": "VERY_LOW",
  "risk_flags": [
    "版本号异常",
    "无官方确认", 
    "技术夸大",
    "水军操作",
    "新账号",
    "完全伪造"
  ],
  "total_confidence": 0.89
}
```

## 🔧 技术栈

### 前端
- React + TypeScript
- Vite 构建工具
- Mock API (演示模式)

### 后端 (FastAPI)
- `/api/v1/intel/enhanced/analyze/enhanced` - 增强分析
- `/api/v1/multiplatform/search` - 多平台搜索
- `/api/v1/multiplatform/aggregate` - 数据聚合
- `/api/v1/multiplatform/analyze-credibility` - 可信度分析

## 🎮 使用步骤

1. 访问 http://localhost:5173
2. 在"深度核验"页面输入待验证内容
3. 选择工具模式（双工/增强核验/多源检索）
4. 点击"发送"开始分析
5. 查看"核验报告"页面的完整推理链

## 📁 项目结构

```
/home/llwxy/aletheia/design/
├── frontend/              # React前端
│   ├── src/
│   │   ├── App.tsx       # 主组件
│   │   ├── api.ts        # API接口定义
│   │   ├── mockApi.ts    # Mock演示数据
│   │   └── App.css       # 样式文件
│   └── dist/             # 构建输出
├── aletheia-backend/     # FastAPI后端
│   ├── api/v1/endpoints/ # API端点
│   ├── services/         # 业务逻辑
│   └── main.py          # 入口文件
└── DEMO_GUIDE.md        # 本文件
```

## ⚠️ 注意事项

1. 当前使用Mock数据进行演示
2. 真实后端需要Redis和PostgreSQL支持
3. LLM分析需要配置SiliconFlow API Key
4. 生产环境请使用真实的后端服务

## 🔗 相关链接

- API文档: http://localhost:8000/docs
- 前端开发: http://localhost:5173
- 项目代码: /home/llwxy/aletheia/design/
