# BettaFish 功能整合总结

## 概述

已成功将 BettaFish 项目的核心功能整合到 Aletheia 项目中，
创建了全新的 `agent_framework` 模块。

---

## 📁 新增文件结构

```
aletheia-backend/services/agent_framework/
├── __init__.py              # 模块导出
├── agent.py                 # VerificationAgent 主类
├── report_generator.py      # 报告生成器
├── bot_detector.py          # 水军检测器
├── state/
│   └── __init__.py          # State 管理（4层嵌套）
├── nodes/
│   └── __init__.py          # 处理节点（6种节点类型）
├── tools/
│   ├── __init__.py          # 关键词优化器
│   └── sentiment.py         # 情感分析器
└── demo.py                  # 使用示例
```

---

## 🎯 移植的功能

### 1. 关键词优化器 (KeywordOptimizer)

**来源**: BettaFish/InsightEngine/tools/keyword_optimizer.py

**功能**:
- 使用 LLM 将用户查询优化为更适合舆情数据库的关键词
- 自动提取10-15个相关关键词
- 避免官方术语，贴近网民语言

**使用**:
```python
from services.agent_framework import KeywordOptimizer

optimizer = KeywordOptimizer()
result = optimizer.optimize("武汉大学舆情管理")
# 输出: ['武大', '武汉大学', '学校管理', ...]
```

---

### 2. 情感分析器 (SentimentAnalyzer)

**来源**: BettaFish/InsightEngine/tools/sentiment_analyzer.py

**功能**:
- 多语言情感分析（支持中文、英文等）
- 5级情感分类：非常负面、负面、中性、正面、非常正面
- 批量分析能力
- 查询结果情感统计

**使用**:
```python
from services.agent_framework import SentimentAnalyzer

analyzer = SentimentAnalyzer()
result = analyzer.analyze("这个产品真的太棒了！")
# 输出: 正面 (置信度: 0.85)
```

---

### 3. 水军检测器 (BotDetector)

**来源**: 基于 BettaFish/MediaCrawler 的账号数据特征开发

**功能**:
- 4维度检测：账号画像、行为模式、内容特征、社交图谱
- 风险评分 (0-1)
- 风险等级分类：low/medium/high
- 批量检测能力

**检测指标**:
- 粉丝关注比异常
- 注册时间过短
- 发帖频率异常
- 内容重复度高
- 发布时间集中

**使用**:
```python
from services.agent_framework import detect_bot

result = detect_bot(
    user_id="user_001",
    follower_count=10,
    following_count=5000,
    post_count=5000
)
# 输出: 风险分 0.85 (high)，可疑账号
```

---

### 4. 报告生成器 (ReportGenerator)

**来源**: BettaFish/ReportEngine/nodes/chapter_generation_node.py

**功能**:
- 基于模板生成结构化报告
- 3种预定义模板：verification/brief/event_analysis
- 自动章节组装
- Markdown + HTML 导出

**模板**:
1. **verification**: 信息核验报告（5章节）
2. **brief**: 简要核验简报（3章节）
3. **event_analysis**: 舆情事件分析报告（7章节）

**使用**:
```python
from services.agent_framework import ReportGenerator

generator = ReportGenerator()
report = generator.generate(state, template="verification")
html = generator.export_to_html(report)
```

---

### 5. Agent 状态管理

**来源**: BettaFish/InsightEngine/state/state.py

**功能**:
- 4层嵌套状态结构
- JSON 序列化/反序列化
- 状态持久化到文件
- 进度追踪

**状态层次**:
```
AgentState
├── VerificationState
│   ├── search_history: List[SearchResult]
│   ├── reasoning_chain: List[ReasoningStep]
│   └── current_summary: str
├── credibility_score: float
├── credibility_level: str
└── risk_flags: List[str]
```

---

### 6. 处理节点系统

**来源**: BettaFish/InsightEngine/nodes/base_node.py

**节点类型**:
- **BaseNode**: 基础抽象节点
- **StateMutationNode**: 状态变更节点
- **SearchNode**: 搜索节点
- **ReasoningNode**: 推理节点
- **SummaryNode**: 总结节点
- **ReflectionNode**: 反思节点

**使用**:
```python
from services.agent_framework import SearchNode, ReasoningNode

search_node = SearchNode(search_tool=my_search_func)
reasoning_node = ReasoningNode(llm_client=my_llm)
```

---

## 🚀 完整验证流程

```python
from services.agent_framework import VerificationAgent

# 创建 Agent
agent = VerificationAgent(
    search_tool=my_search_function,
    enable_keyword_optimization=True,
    enable_sentiment=True,
    max_reflections=2
)

# 执行验证
state = agent.verify("要验证的内容")

# 获取结果
print(f"可信度: {state.credibility_score:.1%}")
print(f"等级: {state.credibility_level}")

# 生成报告
from services.agent_framework import generate_report
report = generate_report(state, template="verification")
```

**验证流程 (6步)**:
1. 关键词优化
2. 多平台搜索
3. 情感分析
4. 推理链构建 (5步)
5. 反思循环
6. 可信度评估

---

## 📊 与原系统的对比

| 功能 | BettaFish | Aletheia (新) | 状态 |
|------|-----------|---------------|------|
| Agent 架构 | 4引擎并行 | VerificationAgent | ✅ 移植完成 |
| 状态管理 | 4层嵌套 | 4层嵌套 | ✅ 移植完成 |
| 关键词优化 | Qwen3优化 | Qwen3优化 | ✅ 移植完成 |
| 情感分析 | 22语言支持 | 规则+LLM | ⚠️ 简化版 |
| 水军检测 | 无明确模块 | 4维度检测 | ✅ 新增 |
| 报告生成 | 章节级生成 | 模板化生成 | ✅ 移植完成 |
| GraphRAG | 知识图谱 | 未移植 | ⏸️ 可选 |

---

## 🔧 配置要求

### 环境变量
```bash
# 关键词优化器 (必需)
KEYWORD_OPTIMIZER_API_KEY=your_api_key
KEYWORD_OPTIMIZER_BASE_URL=https://api.siliconflow.cn/v1
KEYWORD_OPTIMIZER_MODEL_NAME=Qwen/Qwen2.5-7B-Instruct

# 或使用 SiliconFlow 配置
SILICONFLOW_API_KEY=your_api_key
```

### 依赖
```bash
pip install openai loguru
pip install markdown  # 用于 HTML 导出
```

---

## 📝 使用示例

运行演示脚本:
```bash
cd /home/llwxy/aletheia/design/aletheia-backend
python services/agent_framework/demo.py
```

---

## 🎯 后续优化建议

### 短期
1. 集成到现有 API 端点
2. 添加更多报告模板
3. 优化水军检测规则

### 中期
1. 实现 GraphRAG 知识图谱
2. 添加更多平台支持
3. 优化 LLM 提示词

### 长期
1. 训练专用情感分析模型
2. 实现多 Agent 协作
3. 添加可视化报告

---

## 📚 参考

- BettaFish 项目: `/mnt/c/Users/llwxy/BettaFish`
- Aletheia Agent Framework: `services/agent_framework/`
- 使用示例: `services/agent_framework/demo.py`
