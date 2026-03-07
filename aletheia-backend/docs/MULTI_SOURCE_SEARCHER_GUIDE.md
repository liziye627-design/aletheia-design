# 多源新闻搜索器使用指南

## 概述

多源新闻搜索器整合了多个新闻搜索API，实现了智能去重和证据收集功能。

## 支持的搜索源

1. **Tavily API** - 全球新闻搜索
2. **百度千帆 AI 搜索** - 中文新闻搜索
3. **SerpAPI** - Google News 搜索

## 核心功能

### 1. 多源搜索
- 并行搜索多个新闻源
- 自动合并结果
- 统一的数据格式

### 2. 智能去重
- **URL 精确匹配**：相同 URL 的新闻
- **标题相似度**：使用 Jaccard 相似度（阈值 0.85）
- **内容相似度**：使用 SimHash（汉明距离阈值 3）

### 3. 来源优先级
```
1. Tavily (优先级最高)
2. 百度千帆
3. SerpAPI
4. Google News
```

### 4. 合并策略
- **keep_best**: 保留最好的（可信来源 > 内容完整 > 发布时间早）
- **merge_all**: 合并所有来源信息
- **keep_first**: 保留第一个

## 安装依赖

```bash
pip install httpx loguru
```

## 配置环境变量

在 `.env` 文件中添加：

```env
# Tavily API Key
TAVILY_API_KEY=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

# 百度千帆 AI 搜索
BAIDU_QIANFAN_ACCESS_KEY=bce-v3/ALTAK-Ir1AIh4lFWSGIYsr2PR2C/723b00af57d5bd3ec04a17d5290509928120c499

# SerpAPI
SERPAPI_KEY=9918cad702bd1be639fcb5b411e3e76c409f260e1a8a258ba5ff447b4c9f51be
```

## 基本使用

### 1. 多源搜索

```python
import asyncio
import os
from services.crawler.multi_source_news_searcher import MultiSourceNewsSearcher

async def search_news():
    # 初始化搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        baidu_qianfan_key=os.getenv("BAIDU_QIANFAN_ACCESS_KEY"),
        serpapi_key=os.getenv("SERPAPI_KEY"),
    )
    
    # 执行搜索
    result = await searcher.search_all(
        query="两会",
        max_results_per_source=20,
        days=7,
        merge_strategy="keep_best",
    )
    
    # 查看结果
    stats = result["stats"]
    print(f"原始结果: {stats['total_raw_results']}")
    print(f"去重后: {stats['unique_results']}")
    print(f"去重率: {stats['deduplication_rate']:.2%}")
    
    # 遍历结果
    for item in result["results"]:
        print(f"{item.title}")
        print(f"  来源: {item.source}")
        print(f"  URL: {item.url}")
        print(f"  搜索源: {item.search_source.value}")

asyncio.run(search_news())
```

### 2. 指定搜索源

```python
from services.crawler.multi_source_news_searcher import SearchSource

# 只使用特定源
results = await searcher.search_specific(
    query="人工智能",
    sources=[SearchSource.TAVILY, SearchSource.BAIDU_QIANFAN],
    max_results_per_source=15,
    days=7,
)
```

### 3. 证据收集

```python
from services.crawler.multi_source_evidence_collector import (
    MultiSourceEvidenceCollector,
    MultiSourceEvidenceConfig,
)

# 配置
config = MultiSourceEvidenceConfig(
    max_results_per_source=20,
    search_days=7,
    merge_strategy="keep_best",
    min_evidence_count=3,
    min_keyword_hit_rate=0.7,
    min_trusted_hit_rate=0.6,
)

# 初始化收集器
collector = MultiSourceEvidenceCollector(
    multi_source_searcher=searcher,
    config=config,
)

# 收集证据
result = await collector.collect_evidence(query="两会")

# 查看结果
evidence_result = result["evidence_result"]
print(f"证据池: {evidence_result['evidence_count']} 条")
print(f"上下文池: {evidence_result['context_count']} 条")
print(f"质量指标: {evidence_result['quality_metrics']}")
```

### 4. 批量收集

```python
queries = ["两会", "中国维和部队", "日本福岛核事故"]

results = await collector.batch_collect(queries)

# 生成报告
report = collector.generate_report(results)
print(f"总查询数: {report['summary']['total_queries']}")
print(f"证据率: {report['summary']['evidence_rate']:.2%}")
print(f"平均去重率: {report['search_stats']['deduplication_rate']:.2%}")
```

## 去重策略详解

### 1. URL 规范化
- 移除跟踪参数（utm_source, spm, share_token 等）
- 统一域名大小写
- 移除默认端口
- 规范化路径

### 2. 标题相似度
- 移除来源后缀（如 " - 新华社"）
- 使用 Jaccard 相似度
- 阈值：0.85

### 3. 内容相似度
- 使用 SimHash 算法
- 汉明距离阈值：3
- 支持近似重复检测

## 数据结构

### NewsItem
```python
@dataclass
class NewsItem:
    title: str
    url: str
    content: str
    snippet: str
    source: str
    source_domain: str
    publish_time: datetime
    crawl_time: datetime
    search_source: SearchSource
    is_trusted: bool
    url_hash: str
    title_hash: str
    content_hash: str
    simhash: str
    duplicate_of: Optional[str]
    merged_sources: List[SearchSource]
```

### 搜索结果
```python
{
    "stats": {
        "query": str,
        "total_raw_results": int,
        "unique_results": int,
        "deduplication_rate": float,
        "source_stats": dict,
        "trusted_count": int,
        "sources": List[str],
        "domains": List[str],
    },
    "results": List[NewsItem],
}
```

## 测试

运行测试脚本：

```bash
cd aletheia-backend
python tests/integration/test_multi_source_searcher.py
```

测试包括：
1. 多源搜索测试
2. 去重功能测试
3. 证据收集测试
4. 来源优先级测试

## 性能优化建议

1. **并发控制**：使用 `asyncio.gather` 并行搜索多个源
2. **缓存**：对相同查询的结果进行缓存
3. **限流**：控制每个源的请求频率
4. **超时设置**：合理设置请求超时时间

## 常见问题

### Q: 为什么某些搜索源没有结果？
A: 可能的原因：
- API Key 无效或过期
- 搜索查询不合适
- 网络连接问题
- API 限制

### Q: 如何调整去重阈值？
A: 修改 `MultiSourceDeduplicator` 的初始化参数：
```python
deduplicator = MultiSourceDeduplicator(
    title_similarity_threshold=0.90,  # 更严格的标题匹配
    content_similarity_threshold=0.85,  # 更严格的内容匹配
    simhash_threshold=2,  # 更严格的 SimHash 匹配
)
```

### Q: 如何添加新的搜索源？
A: 1. 创建新的搜索器类（继承基础接口）
   2. 在 `SearchSource` 枚举中添加新源
   3. 在 `MultiSourceNewsSearcher` 中注册新源

## 集成到现有流程

### 1. 在调查流程中使用

```python
from services.investigation_helpers import investigate_claim

async def investigate_with_multi_source(claim: str):
    # 使用多源搜索器收集证据
    result = await collector.collect_evidence(claim)
    
    # 转换为标准格式
    evidence_items = [
        {
            "title": item["title"],
            "url": item["url"],
            "source": item["source"],
            "content": item["content"],
            "is_trusted": item["is_trusted"],
        }
        for item in result["evidence_result"]["evidence_pool"]
    ]
    
    # 继续调查流程
    return await investigate_claim(claim, evidence_items)
```

### 2. 在 API 端点中使用

```python
from fastapi import APIRouter
from services.crawler.multi_source_evidence_collector import MultiSourceEvidenceCollector

router = APIRouter()

@router.post("/multi-source-search")
async def multi_source_search(query: str):
    result = await collector.collect_evidence(query)
    return result
```

## 监控和日志

使用 loguru 记录详细日志：

```python
from loguru import logger

logger.info(f"Search query: {query}")
logger.info(f"Found {len(results)} results")
logger.info(f"Deduplication rate: {dedup_rate:.2%}")
```

## 许可证

本模块遵循项目整体许可证。
