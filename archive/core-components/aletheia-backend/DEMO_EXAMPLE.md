# Aletheia 实战演示案例

## 🎯 案例1: 分析"CEO跑路"信息

### 输入
```bash
curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "某CEO卷款跑路，受害者已报警",
    "source_platform": "weibo",
    "metadata": {
      "author_follower_count": 50000,
      "account_age_days": 10,
      "likes": 12000,
      "comments": 3500,
      "shares": 8000
    }
  }'
```

### 系统处理过程

**Step 1**: 提取关键词
```
关键词: ["CEO", "卷款跑路", "报警"]
实体: CEO
```

**Step 2**: 查询历史基准线
```
CEO相关话题过去30天基准:
- 日均提及: 152条
- 标准差: 45条
- 情感分布: 正35% | 中45% | 负20%
```

**Step 3**: 检测异常
```
当前24小时内提及: 1250条
Z-score = (1250 - 152) / 45 = 24.3
→ 异常! (超过3σ阈值)
```

**Step 4**: LLM推理
```
物理层:
- 缺少时间信息 ✗
- 缺少地点信息 ✗
- 缺少转账记录 ✗
- 缺少警方通报 ✗

逻辑层:
- 因果链断裂 ✗
- 逻辑谬误: 3个
  1. 以偏概全
  2. 概念偷换
  3. 诉诸权威

动力学层:
- 账龄10天 → 新账号 🚩
- 互动率: (12000+3500+8000)/50000 = 47% (异常高)
```

**Step 5**: 综合评分
```
初始: 50%
- 物理失败: -20%
- 逻辑谬误(3个): -45%
- 新账号: -20%
- 异常检测: -10%
= -45% → 0%
```

### 输出
```json
{
  "intel": {
    "id": "intel_abc123",
    "credibility_score": 0.0,
    "credibility_level": "VERY_LOW",
    "confidence": "VERY_HIGH",
    "risk_flags": [
      "LOGIC_FALLACY",
      "NEW_ACCOUNT",
      "ANOMALY_DETECTED",
      "WATER_ARMY"
    ],
    "reasoning_chain": [
      "物理层: 缺少时间、地点、转账记录、警方通报等关键物证",
      "逻辑层: 因果链断裂，存在以偏概全、概念偷换等3个逻辑谬误",
      "动力学层: 发布者为10天新账号，发布敏感信息风险极高",
      "动力学层(Layer2): 检测到提及量异常激增+721%，疑似有组织传播"
    ]
  },
  "processing_time_ms": 4523
}
```

---

## 🎯 案例2: 分析真实新闻

### 输入
```bash
curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "特斯拉上海工厂产能突破100万辆，马斯克发推庆祝。根据新华社报道，该工厂于2019年投产，是特斯拉海外首个超级工厂。",
    "source_platform": "weibo",
    "original_url": "https://weibo.com/xinhua/xxxxx",
    "metadata": {
      "author_id": "xinhua",
      "author_name": "新华社",
      "author_follower_count": 15000000,
      "account_age_days": 3650,
      "is_verified": true,
      "likes": 8500,
      "comments": 1200,
      "shares": 3200
    }
  }'
```

### 系统处理过程

**Step 1**: 提取关键词
```
关键词: ["特斯拉", "上海工厂", "100万辆", "马斯克"]
实体: 特斯拉
```

**Step 2**: 基准线查询
```
特斯拉相关话题基准:
- 日均提及: 850条
- 标准差: 120条
- 情感: 正40% | 中45% | 负15%
```

**Step 3**: 异常检测
```
当前提及: 920条
Z-score = (920 - 850) / 120 = 0.58
→ 正常 (小于3σ)
```

**Step 4**: LLM推理
```
物理层:
- 时间: 可验证 ✓ (新华社报道有时间戳)
- 地点: 上海工厂 ✓ (真实存在)
- 事实: 可验证 ✓ (马斯克推特、官方数据)

逻辑层:
- 因果链: 完整 ✓
  前提1: 工厂2019年投产 (可验证)
  前提2: 经过发展达到产能
  结论: 突破100万辆
- 逻辑谬误: 无 ✓

动力学层:
- 发布者: 新华社 (权威媒体) ✓
- 账龄: 10年 ✓
- 粉丝: 1500万 (官方认证) ✓
- 互动率: (8500+1200+3200)/15000000 = 0.086% (正常)
```

**Step 5**: 综合评分
```
初始: 50%
+ 权威媒体: +25%
+ 物理验证通过: +15%
+ 逻辑完整: +10%
= 100% (上限)
```

### 输出
```json
{
  "intel": {
    "id": "intel_xyz789",
    "credibility_score": 0.95,
    "credibility_level": "VERY_HIGH",
    "confidence": "VERY_HIGH",
    "risk_flags": [],
    "reasoning_chain": [
      "物理层: 时间、地点、事实均可验证，有新华社报道和马斯克推特佐证",
      "逻辑层: 因果链完整，前提可验证，结论合理，无逻辑谬误",
      "动力学层: 发布者为新华社(1500万粉丝，10年账龄)，权威性极高",
      "动力学层(Layer2): 提及量正常，未检测到异常信号"
    ]
  },
  "processing_time_ms": 3856
}
```

---

## 🎯 案例3: 微博热搜抓取

### 操作
```bash
docker exec -it aletheia-api python3 << 'PYTHON'
import asyncio
from services.layer1_perception.crawlers.weibo import WeiboCrawler

async def demo():
    crawler = WeiboCrawler()
    
    # 抓取热搜
    hot_topics = await crawler.fetch_hot_topics(limit=10)
    
    print(f"\n✅ 成功抓取{len(hot_topics)}条微博热搜\n")
    
    for i, topic in enumerate(hot_topics, 1):
        print(f"{i}. {topic['content_text']}")
        print(f"   热度: {topic['metadata']['likes']:,}")
        print(f"   平台: {topic['source_platform']}")
        print()
    
    await crawler.close()

asyncio.run(demo())
PYTHON
```

### 输出示例
```
✅ 成功抓取10条微博热搜

1. AI大模型价格战升级
   热度: 1,234,567
   平台: weibo

2. 春节返乡高峰
   热度: 987,654
   平台: weibo

3. 特斯拉降价
   热度: 876,543
   平台: weibo
...
```

---

## 📊 性能测试

### 测试1: 单次分析耗时
```bash
time curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{"content": "测试信息", "source_platform": "weibo"}'
```

**结果**:
```
processing_time_ms: 4523
real: 4.6s
user: 0.1s
sys: 0.0s
```

### 测试2: 缓存命中
```bash
# 第二次请求相同内容
time curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{"content": "测试信息", "source_platform": "weibo"}'
```

**结果**:
```
processing_time_ms: 156  # 从缓存读取
real: 0.2s
user: 0.0s
sys: 0.0s
```

### 测试3: 批量分析
```bash
curl -X POST "http://localhost:8000/api/v1/intel/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"content": "信息1", "source_platform": "weibo"},
      {"content": "信息2", "source_platform": "weibo"},
      {"content": "信息3", "source_platform": "weibo"}
    ]
  }'
```

**结果**:
```
总耗时: 13.2s
平均: 4.4s/条
```

---

## 🔍 调试与监控

### 查看日志
```bash
# 实时日志
docker-compose -f docker/docker-compose.yml logs -f api

# 筛选特定级别
docker logs aletheia-api 2>&1 | grep "ERROR"
```

### 监控指标
访问 http://localhost:3001 (Grafana)

关键指标:
- API响应时间 (P50/P95/P99)
- LLM调用延迟
- 数据库查询时间
- 缓存命中率
- 错误率

### 数据库查询
```bash
docker exec -it aletheia-postgres psql -U aletheia -d aletheia

# 查看最近分析的情报
SELECT id, content_text, credibility_score, analyzed_at 
FROM intels 
ORDER BY analyzed_at DESC 
LIMIT 10;

# 查看异常检测
SELECT entity_name, daily_mention_avg, daily_mention_std 
FROM baselines;
```

---

更多示例请参考: [QUICKSTART.md](QUICKSTART.md)
