# Aletheia 详细 Step 提示词系统

## 概述

借鉴 BettaFish 项目的深度提示词设计，为 Aletheia 的每个 Step 创建了详细具体的提示词，确保：

1. **内容详细具体** - 每个 Step 都有明确的分析维度和输出要求
2. **符合 Step 职责** - 提示词针对 Step 的核心任务定制
3. **信息密度高** - 要求包含具体数据、证据、案例
4. **可验证性强** - 输出包含置信度、证据、疑点

---

## Step 流程 (5步)

```
Step 1: claim_parse          → 命题解析
Step 2: source_verification  → 信源验证
Step 3: cross_validation     → 交叉验证
Step 4: evidence_consistency → 证据一致性
Step 5: final_decision       → 最终决策
```

---

## Step 1: 命题解析 (Claim Parse)

### 目标
将原始命题拆解为可验证的子命题，分析关键要素。

### 分析维度
1. **命题类型判断** - 事实性/观点性/预测性/因果性
2. **核心概念提取** - 关键概念和术语
3. **隐含假设识别** - 隐含的假设和前提
4. **边界界定** - 适用范围和边界条件

### 输出要求
- 拆解为 3-5 个可独立验证的子命题
- 每个子命题包含：时间、地点、人物、事件要素
- reasoning 不少于 200 字
- 包含置信度评分

### 示例输出
```json
{
    "proposition_type": "事实性命题",
    "core_concepts": ["概念1", "概念2"],
    "sub_propositions": [
        {
            "id": 1,
            "content": "子命题内容",
            "verification_criteria": "验证标准",
            "key_elements": {
                "time": "时间要素",
                "location": "地点要素",
                "subjects": ["主体1"],
                "action": "行为要素",
                "result": "结果要素"
            }
        }
    ],
    "reasoning": "详细分析过程...",
    "conclusion": "核心结论",
    "confidence": 0.85
}
```

---

## Step 2: 信源验证 (Source Verification)

### 目标
评估每个信息来源的权威性、可靠性和时效性。

### 评估维度

#### 信源权威性
- **官方媒体** (权重 0.9-1.0) - 新华社、人民日报、央视等
- **专业媒体** (权重 0.7-0.85) - 垂直领域媒体
- **自媒体/UGC** (权重 0.4-0.6) - 微博、公众号等
- **匿名/未知** (权重 0.0-0.3) - 无法追溯来源

#### 内容可信度
- 事实陈述是否有数据支撑
- 观点表达是否明确区分事实
- 引用是否规范
- 逻辑是否一致

#### 时效性
- 最新 (24h) - 权重 1.0
- 近期 (1周) - 权重 0.9
- 一般 (1月) - 权重 0.7
- 过时 (>1月) - 权重 0.5

### 输出要求
- 每个信源给出可信度评分 (0-1)
- 区分高/中/低可信度信源
- 列出可疑特征和疑点
- reasoning 不少于 300 字

### 示例输出
```json
{
    "detailed_source_analysis": [
        {
            "platform": "新华社",
            "credibility_score": 0.95,
            "evidence_quality": "high",
            "key_facts": ["事实1", "事实2"],
            "concerns": []
        }
    ],
    "authoritative_sources": [...],
    "suspicious_indicators": [...],
    "reasoning": "详细评估过程...",
    "confidence": 0.82
}
```

---

## Step 3: 交叉验证 (Cross Validation)

### 目标
通过多源信息交叉验证，识别一致性和矛盾点。

### 验证方法
1. **多源一致性验证**
   - 完全一致 (权重 1.0)
   - 基本一致 (权重 0.8)
   - 部分一致 (权重 0.5)
   - 相互矛盾 (权重 0.0)

2. **证据链完整性**
   - 直接证据
   - 间接证据
   - 证据链条
   - 证据缺失

3. **逻辑一致性**
   - 时间线验证
   - 因果验证
   - 数量验证
   - 常识验证

### 矛盾类型
- **事实性矛盾** - 对同一事实描述相反
- **观点性矛盾** - 对事件解读相反
- **信息缺失型** - 部分信源信息缺失

### 输出要求
- 详细对比各信源的信息
- 列出所有发现的矛盾
- 评估证据链完整性
- reasoning 不少于 400 字

### 示例输出
```json
{
    "consistency_analysis": {
        "overall_consistency": "high",
        "consistency_score": 0.75
    },
    "contradictions_found": [
        {
            "aspect": "时间",
            "conflicting_information": [...],
            "severity": "中等",
            "resolution": "如何处理"
        }
    ],
    "evidence_chain": {
        "direct_evidence": [...],
        "indirect_evidence": [...],
        "weak_links": [...]
    },
    "reasoning": "详细验证过程...",
    "confidence": 0.78
}
```

---

## Step 4: 证据一致性 (Evidence Consistency)

### 目标
评估所有证据的内在一致性和逻辑合理性。

### 评估维度
1. **时间线一致性**
   - 时间顺序合理性
   - 时间戳一致性
   - 时间逻辑验证

2. **空间一致性**
   - 地点描述一致性
   - 空间关系合理性
   - 地理位置合理性

3. **数量逻辑一致性**
   - 数据范围合理性
   - 数量关系协调性
   - 统计口径一致性

4. **人物行为一致性**
   - 行为逻辑验证
   - 陈述一致性

5. **因果关系一致性**
   - 因果逻辑验证
   - 因果链条完整性

### 异常识别
- 逻辑异常 - 违背常识的陈述
- 数据异常 - 不合理的数值
- 行为异常 - 不符合常理的行为

### 输出要求
- 时间线详细分析
- 数据逻辑检查
- 行为合理性评估
- reasoning 不少于 400 字

### 示例输出
```json
{
    "timeline_analysis": {
        "temporal_consistency": "一致",
        "key_timestamps": [...],
        "temporal_anomalies": [...]
    },
    "quantitative_analysis": {
        "numerical_consistency": "一致",
        "quantitative_anomalies": [...]
    },
    "anomalies_summary": [
        {
            "type": "时间异常",
            "description": "描述",
            "severity": "中等",
            "impact": "影响评估"
        }
    ],
    "reasoning": "详细分析过程...",
    "confidence": 0.75
}
```

---

## Step 5: 最终决策 (Final Decision)

### 目标
综合所有推理步骤，给出最终的可信度判定。

### 判定维度
1. **证据充分性** (权重 30%)
   - 高：>10个独立信源
   - 中：5-10个信源
   - 低：<5个信源

2. **证据质量** (权重 25%)
   - 高：多个权威信源
   - 中：混合信源
   - 低：主要为低质量信源

3. **一致性** (权重 20%)
   - 多源一致性
   - 内部一致性

4. **逻辑合理性** (权重 15%)
   - 逻辑严密性
   - 因果合理性

5. **时效性** (权重 10%)
   - 信息新鲜度

### 可信度等级
- **HIGH (0.8-1.0)** - 高度可信
  - 多个权威信源一致证实
  - 证据充分且高质量
  - 无可信反证

- **MEDIUM (0.6-0.79)** - 基本可信
  - 较可靠信源支持
  - 证据基本充分
  - 可能存在轻微疑点

- **LOW (0.4-0.59)** - 可信度低
  - 信源可信度不高
  - 证据不充分
  - 存在未解决矛盾

- **UNCERTAIN (0-0.39)** - 无法确定
  - 证据严重不足
  - 存在严重矛盾
  - 有力反证

### 输出要求
- 完整评分分解
- 关键支持证据和反证
- 风险标记
- 决策建议
- reasoning 不少于 500 字

### 示例输出
```json
{
    "decision_summary": {
        "final_credibility_score": 0.78,
        "credibility_level": "MEDIUM",
        "truth_status": "基本属实"
    },
    "scoring_breakdown": {
        "evidence_sufficiency": {"score": 0.25, "weight": 0.30, ...},
        "evidence_quality": {"score": 0.85, "weight": 0.25, ...},
        "consistency": {"score": 0.80, "weight": 0.20, ...},
        "logical_soundness": {"score": 0.75, "weight": 0.15, ...},
        "timeliness": {"score": 0.90, "weight": 0.10, ...},
        "total_score": 0.78
    },
    "key_supporting_evidence": [...],
    "key_contradictory_evidence": [...],
    "risk_flags": ["NEEDS_CONTEXT"],
    "recommendations": {
        "for_decision_making": "决策建议",
        "for_further_verification": "进一步验证建议",
        "caveats": "使用时的注意事项"
    },
    "reasoning": "最终决策详细推理...",
    "confidence": 0.78
}
```

---

## 使用方法

### 基础用法
```python
from services.agent_framework import EnhancedVerificationAgent

agent = EnhancedVerificationAgent(
    search_tool=my_search_function,
    use_llm_reasoning=True  # 启用 LLM 推理
)

state = agent.verify("要验证的内容")

# 查看详细推理结果
for step in state.verification.reasoning_chain:
    print(f"Step {step.step}: {step.stage}")
    print(f"推理: {step.reasoning[:200]}...")
    print(f"结论: {step.conclusion}")
    print(f"置信度: {step.confidence}")
```

### 查看特定 Step 的详细内容
```python
from services.agent_framework import get_step_prompt

# 获取 Step 的提示词
prompt = get_step_prompt("source_verification")
print(prompt["name"])  # 信源验证
print(prompt["system_prompt"])  # 完整的系统提示词
```

### 单独调用 LLM 推理
```python
from services.agent_framework import generate_step_reasoning

result = generate_step_reasoning(
    step_key="cross_validation",
    state_data=state_dict,
    search_results=search_results,
    previous_steps=previous_steps
)

print(result["reasoning"])
print(result["conclusion"])
print(result["confidence"])
```

---

## 提示词设计特点

### 1. 结构化输出
每个 Step 都有明确的 JSON Schema，确保输出格式一致。

### 2. 详细要求
- reasoning 字段有字数要求 (200-800字)
- 必须包含具体证据
- 必须列出疑点和风险

### 3. 可量化的评估
- 置信度评分 (0-1)
- 影响力评分 (score_impact)
- 等级分类 (high/medium/low)

### 4. 上下文感知
- 可以使用之前的 Step 结果
- 可以访问所有搜索结果
- 可以看到命题原文

---

## 对比：简单 vs 详细提示词

### 简单提示词
```
请分析信源可信度，给出结论和置信度。
```

### 详细提示词
```
你是一位资深的信源评估专家...

评估维度：
1. 信源权威性（官方/专业/自媒体/匿名）
2. 内容可信度（事实/观点/引用/逻辑）
3. 时效性（最新/近期/一般/过时）

评估标准：
- 高可信度：官方媒体、具体数据、可验证
- 中可信度：专业媒体、部分验证
- 低可信度：自媒体、缺乏证据

输出格式：
{
    "detailed_source_analysis": [...],
    "reasoning": "详细评估过程（300-500字）",
    "conclusion": "结论",
    "confidence": 0.82
}
```

---

## 优势

1. **内容质量高** - 详细要求确保输出内容丰富
2. **一致性好** - 结构化输出便于后续处理
3. **可追溯性强** - 详细的 reasoning 便于审查
4. **符合需求** - 每个 Step 针对特定任务定制
5. **可扩展性好** - 易于添加新的 Step 或修改提示词
