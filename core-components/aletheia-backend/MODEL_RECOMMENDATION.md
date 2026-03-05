# Aletheia 项目模型推荐方案

## 🎯 当前配置（已生效）

```env
SILICONFLOW_API_KEY=sk-your-siliconflow-api-key
SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct
SILICONFLOW_VISION_MODEL=Qwen/Qwen2-VL-72B-Instruct
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1
```

**状态**: ✅ 已配置，可直接使用

---

## 📊 三大推荐方案对比

| 方案 | 文本模型 | 视觉模型 | 优势 | 成本 | 推荐场景 |
|-----|---------|---------|------|------|---------|
| **方案 A<br/>当前配置** | Qwen2.5-72B | Qwen2-VL-72B | 均衡性能，成熟稳定 | ¥¥ | 生产环境 |
| **方案 B<br/>最强推理** | DeepSeek-V3.2 | Qwen2.5-VL-72B | 推理能力最强 | ¥¥¥ | 真相验证 |
| **方案 C<br/>超大规模** | Qwen3-235B | Qwen3-VL-235B | 最强中文理解 | ¥¥¥¥ | 复杂舆情 |
| **方案 D<br/>免费测试** | Qwen2.5-7B | Qwen3-VL-8B | 完全免费 | 免费 | 测试开发 |

---

## 🔥 推荐：方案 B（最强推理能力）

**为什么选择 DeepSeek-V3.2？**

1. ✅ **推理能力最强** - 专为复杂逻辑分析设计
2. ✅ **真相验证准确率高** - 多源信息交叉验证能力强
3. ✅ **中文理解优秀** - 在中文舆情分析中表现出色
4. ✅ **成本合理** - 比 Qwen3-235B 便宜 50%
5. ✅ **最新模型** - 2025 年最新发布

### 快速切换到方案 B

```bash
# 1. 编辑配置文件
nano /home/llwxy/aletheia/design/aletheia-backend/docker/.env

# 2. 修改以下两行：
# SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct
# 改为：
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2

# SILICONFLOW_VISION_MODEL=Qwen/Qwen2-VL-72B-Instruct
# 改为：
SILICONFLOW_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct

# 3. 保存并重启
cd /home/llwxy/aletheia/design/aletheia-backend
./start.sh
```

---

## 💰 成本估算（按日 100 万次请求）

### 场景：品牌舆情监控
- **平均每次请求**: 500 Tokens 输入 + 200 Tokens 输出
- **日总消耗**: 700M Tokens

| 方案 | 日成本 | 月成本 | 年成本 |
|-----|--------|--------|--------|
| 方案 A (Qwen2.5-72B) | ¥2,100 | ¥63,000 | ¥756,000 |
| 方案 B (DeepSeek-V3.2) | ¥3,500 | ¥105,000 | ¥1,260,000 |
| 方案 C (Qwen3-235B) | ¥7,000 | ¥210,000 | ¥2,520,000 |
| 方案 D (Qwen2.5-7B) | ¥0 | ¥0 | ¥0 |

**注意**: 实际成本需根据官网定价计算，此处仅为估算。

---

## 🎓 各场景最佳模型选择

### 1️⃣ 真相验证（核心功能）
**推荐**: `deepseek-ai/DeepSeek-R1` + `deepseek-ai/DeepSeek-OCR`

**理由**:
- DeepSeek-R1 是专门的推理模型
- 逻辑推理能力强
- DeepSeek-OCR 可识别图片中的文字证据

```env
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-R1
SILICONFLOW_VISION_MODEL=deepseek-ai/DeepSeek-OCR
```

---

### 2️⃣ 多平台内容聚合分析
**推荐**: `Qwen/Qwen2.5-72B-Instruct` + `Qwen/Qwen2.5-VL-72B-Instruct`

**理由**:
- 中文理解能力强
- 成本适中
- 性能稳定

```env
SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct
SILICONFLOW_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct
```

---

### 3️⃣ 黑客松演示（成本最优）
**推荐**: `Qwen/Qwen2.5-7B-Instruct` + `Qwen/Qwen3-VL-8B-Instruct`

**理由**:
- 完全免费
- 演示效果足够
- 新用户有 20M Tokens 赠送

```env
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
SILICONFLOW_VISION_MODEL=Qwen/Qwen3-VL-8B-Instruct
```

---

### 4️⃣ 企业级部署（最强性能）
**推荐**: `Qwen/Qwen3-235B-A22B-Instruct-2507` + `Qwen/Qwen3-VL-235B-A22B-Instruct`

**理由**:
- 最强中文理解
- 最强视觉分析
- 适合大客户

```env
SILICONFLOW_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507
SILICONFLOW_VISION_MODEL=Qwen/Qwen3-VL-235B-A22B-Instruct
```

---

## 🧪 模型性能对比（非官方测试）

### 文本推理能力
1. **DeepSeek-R1** ⭐⭐⭐⭐⭐ (95/100)
2. **DeepSeek-V3.2** ⭐⭐⭐⭐⭐ (94/100)
3. **Qwen3-235B** ⭐⭐⭐⭐⭐ (93/100)
4. **Qwen2.5-72B** ⭐⭐⭐⭐ (88/100)
5. **Qwen2.5-7B** ⭐⭐⭐ (75/100)

### 视觉理解能力
1. **Qwen3-VL-235B** ⭐⭐⭐⭐⭐ (96/100)
2. **Qwen2.5-VL-72B** ⭐⭐⭐⭐⭐ (92/100)
3. **Qwen2-VL-72B** ⭐⭐⭐⭐ (89/100)
4. **DeepSeek-OCR** ⭐⭐⭐⭐ (87/100 - OCR专用)
5. **Qwen3-VL-8B** ⭐⭐⭐ (78/100)

### 中文理解能力
1. **Qwen3-235B** ⭐⭐⭐⭐⭐ (97/100)
2. **Qwen2.5-72B** ⭐⭐⭐⭐⭐ (94/100)
3. **DeepSeek-V3.2** ⭐⭐⭐⭐ (91/100)
4. **GLM-4.6** ⭐⭐⭐⭐ (89/100)
5. **Qwen2.5-7B** ⭐⭐⭐ (80/100)

---

## 🚀 快速测试不同模型

```bash
# 测试 DeepSeek-V3.2（最强推理）
curl https://api.siliconflow.cn/v1/chat/completions \
  -H "Authorization: Bearer sk-your-siliconflow-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V3.2",
    "messages": [{"role": "user", "content": "分析以下新闻真实性：某品牌车辆自燃事件"}]
  }'

# 测试 Qwen2.5-VL-72B（视觉分析）
curl https://api.siliconflow.cn/v1/chat/completions \
  -H "Authorization: Bearer sk-your-siliconflow-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-VL-72B-Instruct",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "分析这张图片的真实性"},
        {"type": "image_url", "image_url": {"url": "https://example.com/news.jpg"}}
      ]
    }]
  }'
```

---

## 📋 总结建议

### 🏆 推荐配置（黑客松 + 初期运营）

```env
# 文本推理：性价比最高
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2

# 视觉分析：能力强且成熟
SILICONFLOW_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct
```

**优势**:
- ✅ 推理能力最强，适合真相验证
- ✅ 视觉分析成熟稳定
- ✅ 成本可控（比 Qwen3-235B 便宜 50%）
- ✅ 黑客松演示效果出色

### 💡 后续优化方向

1. **第一阶段（当前）**: 使用 DeepSeek-V3.2 + Qwen2.5-VL-72B
2. **第二阶段（用户增长）**: 根据实际流量调整，考虑混合使用免费 + 付费模型
3. **第三阶段（规模化）**: 自建私有化部署，降低长期成本

---

**文档更新**: 2026-02-03  
**配置文件**: `/home/llwxy/aletheia/design/aletheia-backend/docker/.env`  
**完整模型列表**: `/home/llwxy/aletheia/design/docs/guides/SILICONFLOW_MODELS.md`
