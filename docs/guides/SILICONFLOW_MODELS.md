# 硅基流动（SiliconFlow）模型列表参考

**API Key 已配置**: `sk-your-siliconflow-api-key`  
**API Base URL**: `https://api.siliconflow.cn/v1`  
**兼容性**: OpenAI API 兼容格式

---

## 📋 Aletheia 项目当前使用的模型

| 功能模块 | 模型 ID | 说明 |
|---------|---------|------|
| **文本推理** | `Qwen/Qwen2.5-72B-Instruct` | 通用对话、内容分析 |
| **视觉分析** | `Qwen/Qwen2-VL-72B-Instruct` | 图片理解、情感分析 |

---

## 🔥 推荐替换方案（性能更强）

### 方案 1: 最强推理能力
```bash
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
SILICONFLOW_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct
```
**优势**: DeepSeek-V3.2 是最新模型，推理能力更强，适合真相验证

### 方案 2: 超大规模模型
```bash
SILICONFLOW_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507
SILICONFLOW_VISION_MODEL=Qwen/Qwen3-VL-235B-A22B-Instruct
```
**优势**: 最强中文理解能力，适合复杂舆情分析

### 方案 3: DeepSeek 推理专用
```bash
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-R1
SILICONFLOW_VISION_MODEL=deepseek-ai/DeepSeek-OCR
```
**优势**: 推理模型 + OCR 专用，适合图文验证

---

## 📊 完整模型列表

### 1. 大语言模型（LLM - 对话/推理）

#### 顶级模型（旗舰级）
- `deepseek-ai/DeepSeek-V3.2` - DeepSeek V3.2（最新）
- `deepseek-ai/DeepSeek-R1` - 推理专用模型
- `Qwen/Qwen3-235B-A22B-Instruct-2507` - Qwen3 235B（超大规模）
- `Qwen/Qwen3-Next-80B-A3B-Instruct` - Qwen3 Next 80B
- `Pro/deepseek-ai/DeepSeek-V3.2` - DeepSeek V3.2 Pro 版本

#### 高性能模型（推荐使用）
- `Qwen/Qwen2.5-72B-Instruct` - Qwen2.5 72B（当前使用）
- `Qwen/Qwen2.5-72B-Instruct-128K` - Qwen2.5 72B 长上下文版
- `deepseek-ai/DeepSeek-V2.5` - DeepSeek V2.5
- `zai-org/GLM-4.6` - 智谱 GLM-4.6
- `stepfun-ai/step3` - 阶跃星辰 Step-3
- `baidu/ERNIE-4.5-300B-A47B` - 百度文心 ERNIE-4.5

#### 中等规模模型（成本友好）
- `Qwen/Qwen2.5-32B-Instruct` - Qwen2.5 32B
- `Qwen/Qwen2.5-14B-Instruct` - Qwen2.5 14B
- `Qwen/Qwen2.5-7B-Instruct` - Qwen2.5 7B（免费）
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` - DeepSeek R1 蒸馏版 32B
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-14B` - DeepSeek R1 蒸馏版 14B
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` - DeepSeek R1 蒸馏版 7B

#### 推理/思考模型
- `deepseek-ai/DeepSeek-R1` - DeepSeek 推理模型
- `Qwen/QwQ-32B` - Qwen 思考模型 32B
- `Qwen/Qwen3-30B-A3B-Thinking-2507` - Qwen3 思考模型
- `moonshotai/Kimi-K2-Thinking` - Kimi K2 思考版
- `THUDM/GLM-Z1-32B-0414` - GLM-Z1 推理模型

#### 代码专用模型
- `Qwen/Qwen3-Coder-480B-A35B-Instruct` - Qwen3 Coder 480B
- `Qwen/Qwen3-Coder-30B-A3B-Instruct` - Qwen3 Coder 30B
- `Qwen/Qwen2.5-Coder-32B-Instruct` - Qwen2.5 Coder 32B
- `Qwen/Qwen2.5-Coder-7B-Instruct` - Qwen2.5 Coder 7B（免费）

---

### 2. 多模态视觉模型（Vision - 图片分析）

#### 超大视觉模型
- `Qwen/Qwen3-VL-235B-A22B-Instruct` - Qwen3 VL 235B（最强）
- `Qwen/Qwen2.5-VL-72B-Instruct` - Qwen2.5 VL 72B
- `Qwen/Qwen2-VL-72B-Instruct` - Qwen2 VL 72B（当前使用）

#### 中等视觉模型
- `Qwen/Qwen3-VL-32B-Instruct` - Qwen3 VL 32B
- `Qwen/Qwen2.5-VL-32B-Instruct` - Qwen2.5 VL 32B
- `Qwen/Qwen3-VL-8B-Instruct` - Qwen3 VL 8B

#### 视觉推理模型
- `Qwen/Qwen3-VL-235B-A22B-Thinking` - Qwen3 VL 思考版
- `Qwen/Qwen3-VL-32B-Thinking` - Qwen3 VL 32B 思考版
- `Qwen/QVQ-72B-Preview` - Qwen 视觉问答模型

#### OCR 专用模型
- `deepseek-ai/DeepSeek-OCR` - DeepSeek OCR（文字识别专用）
- `PaddlePaddle/PaddleOCR-VL-1.5` - 百度 PaddleOCR

#### 其他视觉模型
- `zai-org/GLM-4.6V` - 智谱 GLM-4.6 视觉版
- `zai-org/GLM-4.5V` - 智谱 GLM-4.5 视觉版
- `deepseek-ai/deepseek-vl2` - DeepSeek VL2

---

### 3. 语音模型（Audio）

#### 语音识别（ASR - Speech to Text）
- `FunAudioLLM/SenseVoiceSmall` - 阿里 SenseVoice（高质量）
- `TeleAI/TeleSpeechASR` - 字节跳动 ASR

#### 文字转语音（TTS - Text to Speech）
- `fishaudio/fish-speech-1.5` - Fish Speech 1.5（推荐）
- `fishaudio/fish-speech-1.4` - Fish Speech 1.4
- `FunAudioLLM/CosyVoice2-0.5B` - 阿里 CosyVoice2
- `IndexTeam/IndexTTS-2` - Index TTS 2
- `fnlp/MOSS-TTSD-v0.5` - 复旦 MOSS TTS
- `RVC-Boss/GPT-SoVITS` - GPT-SoVITS（克隆音色）

---

### 4. 图片生成模型（Image Generation）

#### FLUX 系列（最强图片生成）
- `black-forest-labs/FLUX.1-pro` - FLUX.1 Pro（最高质量）
- `black-forest-labs/FLUX.1-dev` - FLUX.1 Dev（开发版）
- `black-forest-labs/FLUX.1-schnell` - FLUX.1 Schnell（快速版）

#### 其他图片生成
- `Kwai-Kolors/Kolors` - 快手可图（中文理解强）
- `Qwen/Qwen-Image` - Qwen 图片生成
- `Qwen/Qwen-Image-Edit` - Qwen 图片编辑
- `Qwen/Qwen-Image-Edit-2509` - Qwen 图片编辑 2509

---

### 5. 视频生成模型（Video Generation）

- `Wan-AI/Wan2.2-T2V-A14B` - Wan2.2 文字生成视频
- `Wan-AI/Wan2.2-I2V-A14B` - Wan2.2 图片生成视频

---

### 6. Embedding & Reranker（向量化/重排序）

#### Embedding 模型
- `BAAI/bge-m3` - BGE M3（多语言）
- `BAAI/bge-large-zh-v1.5` - BGE Large 中文版
- `BAAI/bge-large-en-v1.5` - BGE Large 英文版
- `netease-youdao/bce-embedding-base_v1` - 网易 BCE Embedding
- `Qwen/Qwen3-Embedding-8B` - Qwen3 Embedding 8B
- `Qwen/Qwen3-Embedding-4B` - Qwen3 Embedding 4B
- `Qwen/Qwen3-Embedding-0.6B` - Qwen3 Embedding 0.6B

#### Reranker 模型
- `BAAI/bge-reranker-v2-m3` - BGE Reranker V2 M3
- `netease-youdao/bce-reranker-base_v1` - 网易 BCE Reranker
- `Qwen/Qwen3-Reranker-8B` - Qwen3 Reranker 8B
- `Qwen/Qwen3-Reranker-4B` - Qwen3 Reranker 4B
- `Qwen/Qwen3-Reranker-0.6B` - Qwen3 Reranker 0.6B

---

## 💡 使用建议

### 场景 1: 文本真相验证（推理为主）
**推荐模型**: `deepseek-ai/DeepSeek-R1` 或 `deepseek-ai/DeepSeek-V3.2`  
**理由**: 推理能力最强，适合逻辑分析和多源验证

### 场景 2: 图片真伪鉴别（视觉分析）
**推荐模型**: `Qwen/Qwen2.5-VL-72B-Instruct` + `deepseek-ai/DeepSeek-OCR`  
**理由**: 强视觉理解 + OCR 识别图片中的文字

### 场景 3: 成本优化（免费模型）
**推荐模型**: `Qwen/Qwen2.5-7B-Instruct` + `Qwen/Qwen3-VL-8B-Instruct`  
**理由**: 小规模模型免费使用，适合测试和小流量场景

### 场景 4: 最强性能（不计成本）
**推荐模型**: `Qwen/Qwen3-235B-A22B-Instruct-2507` + `Qwen/Qwen3-VL-235B-A22B-Instruct`  
**理由**: 最强中文理解和视觉能力

---

## 🔧 如何切换模型

### 方法 1: 修改 `.env` 文件
```bash
nano /home/llwxy/aletheia/design/aletheia-backend/docker/.env

# 修改以下行：
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
SILICONFLOW_VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct

# 保存后重启服务
cd /home/llwxy/aletheia/design/aletheia-backend
./start.sh
```

### 方法 2: API 调用时动态指定
```python
import openai

client = openai.OpenAI(
    api_key="sk-your-siliconflow-api-key",
    base_url="https://api.siliconflow.cn/v1"
)

# 使用不同模型
response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V3.2",  # 这里指定模型
    messages=[{"role": "user", "content": "分析这段新闻的真实性"}]
)
```

---

## 📊 价格参考（仅供参考，请以官网为准）

| 模型规模 | 示例模型 | 价格（¥/百万 Token）|
|---------|---------|---------------------|
| **免费** | Qwen2.5-7B | 免费 |
| **小模型** | Qwen2.5-14B | ~¥0.5 |
| **中等模型** | Qwen2.5-32B | ~¥1.5 |
| **大模型** | Qwen2.5-72B | ~¥3.0 |
| **超大模型** | DeepSeek-V3.2 | ~¥5.0 |
| **旗舰模型** | Qwen3-235B | ~¥10.0 |

**注意**: 
- 新用户注册赠送 20M Tokens
- 部分模型限时免费
- Pro 版本模型价格更高但性能更稳定

---

## 🔗 相关链接

- **官网**: https://siliconflow.cn
- **控制台**: https://cloud.siliconflow.cn
- **API 文档**: https://docs.siliconflow.cn
- **模型列表**: https://docs.siliconflow.cn/cn/userguide/capabilities/text-generation.md
- **定价**: https://siliconflow.cn/pricing

---

**最后更新**: 2026-02-03  
**文档维护**: Aletheia 项目组
