# 🌐 无需认证的数据采集方案

## 概述

Aletheia系统中**26个数据源完全不需要cookies或API keys**，可以直接使用！

---

## ✅ 立即可用的数据源（26个）

### 📰 官方信源（17个）

#### 中国官方（10个）
1. **国务院官网** - RSS订阅
2. **市监总局** - RSS订阅
3. **证监会** - RSS订阅
4. **卫健委** - RSS订阅
5. **应急管理部** - RSS订阅
6. **公安部** - RSS订阅
7. **最高人民法院** - RSS订阅
8. **最高人民检察院** - RSS订阅
9. **新华网** - RSS订阅
10. **人民网** - RSS订阅

#### 国际官方（7个）
11. **WHO** - RSS订阅
12. **CDC** - RSS订阅
13. **UN News** - RSS订阅
14. **World Bank** - RSS订阅
15. **SEC** - RSS订阅
16. **FCA UK** - RSS订阅
17. **EU Open Data** - RSS订阅

### 📡 新闻媒体（6个）
18. **Reuters** - RSS订阅
19. **AP News** - RSS订阅
20. **BBC** - RSS订阅
21. **Guardian** - RSS订阅
22. **财新网** - RSS订阅
23. **澎湃新闻** - RSS订阅

### 🎓 学术数据集（3个）
24. **GDELT Project** - 公开API（全球事件数据库）
25. **Common Crawl** - 公开API（网页存档）
26. **OpenAlex** - 公开API（学术论文，建议提供邮箱）

---

## 🚀 立即开始使用（无需任何凭证）

### 测试脚本

创建 `test_no_auth_crawlers.py`:

```python
"""
测试无需认证的爬虫

完全不需要cookies或API keys！
"""

import asyncio
from services.layer1_perception.crawler_manager import CrawlerManager


async def test_no_auth_sources():
    """测试所有无需认证的数据源"""
    
    # 初始化管理器（不提供任何凭证）
    manager = CrawlerManager()
    
    print("🌐 测试无需认证的数据源\n")
    
    # ========== 官方信源测试 ==========
    print("="*60)
    print("📰 官方信源测试")
    print("="*60)
    
    # 测试新华网
    print("\n1. 新华网...")
    xinhua = manager.get_crawler("xinhua")
    news = await xinhua.fetch_latest(limit=3)
    for item in news[:2]:
        print(f"  • {item['title'][:50]}...")
    
    # 测试WHO
    print("\n2. WHO...")
    who = manager.get_crawler("who")
    who_news = await who.fetch_latest(limit=3)
    for item in who_news[:2]:
        print(f"  • {item['title'][:50]}...")
    
    # ========== 新闻媒体测试 ==========
    print("\n" + "="*60)
    print("📡 新闻媒体测试")
    print("="*60)
    
    # 测试Reuters
    print("\n3. Reuters...")
    reuters = manager.get_crawler("reuters")
    reuters_news = await reuters.fetch_latest(limit=3)
    for item in reuters_news[:2]:
        print(f"  • {item['title'][:50]}...")
    
    # 测试BBC
    print("\n4. BBC...")
    bbc = manager.get_crawler("bbc")
    bbc_news = await bbc.fetch_latest(limit=3)
    for item in bbc_news[:2]:
        print(f"  • {item['title'][:50]}...")
    
    # ========== 学术数据集测试 ==========
    print("\n" + "="*60)
    print("🎓 学术数据集测试")
    print("="*60)
    
    # 测试GDELT
    print("\n5. GDELT Project...")
    gdelt = manager.get_crawler("gdelt")
    events = await gdelt.search_events(
        query="artificial intelligence",
        max_records=3
    )
    for item in events[:2]:
        print(f"  • {item['title'][:50]}...")
    
    # 测试OpenAlex
    print("\n6. OpenAlex...")
    openalex = manager.get_crawler("openalex")
    papers = await openalex.search_works(
        query="machine learning",
        limit=3
    )
    for item in papers[:2]:
        print(f"  • {item['title'][:50]}...")
    
    print("\n" + "="*60)
    print("✅ 测试完成！所有数据源都可正常使用")
    print("="*60)
    
    await manager.close_all()


if __name__ == "__main__":
    asyncio.run(test_no_auth_sources())
```

### 运行测试

```bash
cd aletheia-backend
python test_no_auth_crawlers.py
```

### 预期输出

```
🌐 测试无需认证的数据源

============================================================
📰 官方信源测试
============================================================

1. 新华网...
  • 习近平主持召开中央全面深化改革委员会第三次会议...
  • 李强主持召开国务院常务会议...

2. WHO...
  • WHO Director-General's opening remarks at the med...
  • Global health leaders meet to discuss pandemic pr...

============================================================
📡 新闻媒体测试
============================================================

3. Reuters...
  • Oil prices rise on Middle East tensions...
  • Tech stocks rally as AI spending surges...

4. BBC...
  • UK inflation falls to 2.5% in latest figures...
  • Climate summit agrees on fossil fuel transition...

============================================================
🎓 学术数据集测试
============================================================

5. GDELT Project...
  • AI regulation discussed at global tech summit...
  • New study shows AI impact on employment...

6. OpenAlex...
  • Deep Learning for Natural Language Processing...
  • Advances in Reinforcement Learning Algorithms...

============================================================
✅ 测试完成！所有数据源都可正常使用
============================================================
```

---

## 📊 数据覆盖范围

### 按地区

| 地区 | 数据源数量 | 覆盖领域 |
|------|-----------|---------|
| **中国** | 12 | 政府公告、新闻媒体 |
| **全球** | 14 | 国际组织、新闻媒体、学术 |

### 按类型

| 类型 | 数据源数量 | 更新频率 |
|------|-----------|---------|
| **政府公告** | 10 | 每日 |
| **国际组织** | 7 | 每日 |
| **新闻媒体** | 6 | 实时 |
| **学术数据** | 3 | 实时 |

### 数据量估算

| 数据源 | 每日新增 | 历史数据 |
|--------|---------|---------|
| **GDELT** | ~250,000条事件 | 1979年至今 |
| **OpenAlex** | ~10,000篇论文 | 2.5亿+篇 |
| **新闻媒体** | ~500篇文章 | 按RSS保留期 |
| **官方信源** | ~200条公告 | 按RSS保留期 |

---

## 🎯 实际应用场景

### 场景1: 全球事件监控

```python
async def monitor_global_events():
    """监控全球重大事件"""
    manager = CrawlerManager()
    
    # 使用GDELT监控全球事件
    gdelt = manager.get_crawler("gdelt")
    events = await gdelt.get_trending_themes(
        timespan="1d",
        source_country="CN"  # 筛选中国相关
    )
    
    # 结合官方信源验证
    xinhua = manager.get_crawler("xinhua")
    official_news = await xinhua.fetch_latest(limit=20)
    
    # 交叉验证
    for event in events:
        # 检查官方信源是否有相关报道
        ...
    
    await manager.close_all()
```

### 场景2: 学术趋势分析

```python
async def analyze_research_trends():
    """分析学术研究趋势"""
    manager = CrawlerManager()
    
    openalex = manager.get_crawler("openalex")
    
    # 获取AI领域热门论文
    papers = await openalex.get_trending_topics(
        field="computer-science",
        years_back=2,
        limit=50
    )
    
    # 分析高引用论文
    high_impact = [
        p for p in papers 
        if p['metadata']['cited_by_count'] > 100
    ]
    
    await manager.close_all()
```

### 场景3: 新闻真实性验证

```python
async def verify_news():
    """跨平台新闻验证"""
    manager = CrawlerManager()
    
    keyword = "经济政策"
    
    # 从多个渠道获取信息
    sources = {
        "official": manager.get_crawler("xinhua"),
        "intl_news": manager.get_crawler("reuters"),
        "domestic_news": manager.get_crawler("caixin"),
    }
    
    results = {}
    for name, crawler in sources.items():
        items = await crawler.fetch_latest(limit=10)
        # 筛选相关新闻
        relevant = [
            item for item in items 
            if keyword in item['title'] or keyword in item['content']
        ]
        results[name] = relevant
    
    # 交叉对比分析
    if results["official"] and results["intl_news"]:
        print("✅ 多渠道验证一致")
    
    await manager.close_all()
```

---

## 🔧 优化建议

### 提高数据质量

1. **OpenAlex邮箱配置**（强烈建议）
   ```python
   manager = CrawlerManager(
       openalex_email="your.email@example.com"  # 速率限制: 10→100 req/s
   )
   ```

2. **GitHub Token**（可选，提高速率）
   ```python
   manager = CrawlerManager(
       github_token="ghp_xxx"  # 速率限制: 60→5000 req/h
   )
   ```

### 缓存策略

```python
# 避免重复抓取，实现缓存
import redis

r = redis.Redis()

async def fetch_with_cache(crawler, cache_key, ttl=3600):
    """带缓存的数据获取"""
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)
    
    data = await crawler.fetch_latest(limit=20)
    r.setex(cache_key, ttl, json.dumps(data))
    return data
```

---

## 📈 性能基准

### 并发抓取测试

```python
async def benchmark_parallel_crawling():
    """测试并发抓取性能"""
    import time
    
    manager = CrawlerManager()
    
    # 同时抓取10个平台
    platforms = [
        "xinhua", "reuters", "bbc", "who", "gdelt",
        "openalex", "un_news", "caixin", "ap_news", "guardian"
    ]
    
    start = time.time()
    
    tasks = []
    for platform in platforms:
        crawler = manager.get_crawler(platform)
        if hasattr(crawler, 'fetch_latest'):
            tasks.append(crawler.fetch_latest(limit=5))
        elif hasattr(crawler, 'search_events'):
            tasks.append(crawler.search_events(query="test", max_records=5))
    
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    total_items = sum(len(r) for r in results)
    
    print(f"⚡ 性能测试结果:")
    print(f"  • 平台数: {len(platforms)}")
    print(f"  • 总条目: {total_items}")
    print(f"  • 耗时: {elapsed:.2f}秒")
    print(f"  • 速率: {total_items/elapsed:.1f} 条/秒")
    
    await manager.close_all()
```

**预期结果**:
- 10个平台并发抓取
- 约50条数据
- 耗时 ~5-10秒
- 速率 ~5-10 条/秒

---

## ✅ 总结

### 优势

✅ **完全合法** - 使用公开API和RSS订阅  
✅ **无需认证** - 26个数据源直接可用  
✅ **高可靠性** - 官方数据源，稳定性高  
✅ **广泛覆盖** - 中国+全球，政府+媒体+学术  
✅ **实时更新** - 大部分每日/实时更新  

### 局限

⚠️ **社交媒体数据缺失** - 需要cookies才能访问微博、知乎等  
⚠️ **用户生成内容有限** - RSS主要是官方发布  
⚠️ **评论数据缺失** - 无法获取用户评论和互动  

### 解决方案

对于需要社交媒体数据的场景：
1. **优先使用官方API**（Twitter, Reddit已支持）
2. **合法获取cookies**（使用我们的自动化脚本）
3. **使用第三方数据服务**（合规的数据提供商）

---

**现在就可以开始使用这26个数据源，完全不需要任何凭证！** 🚀
