# Evidence Library Integration Guide
# 证据库集成指南

## 概述

证据库模块实现了两段式采集模型，将 Layer1 感知层爬虫与证据存储/检索系统集成。

```
┌─────────────────────────────────────────────────────────────────┐
│                    Crawler Output                                │
│                    (Standardized Format)                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EvidencePipeline                              │
│   1. Create SearchHit (Discovery Record)                         │
│   2. Fetch Detail Page                                           │
│   3. Extract Content (Template → JSON-LD → OG → Fallback)        │
│   4. Create EvidenceDoc with Scoring                             │
│   5. Deduplication & Version Management                          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                 │
│   - MetaDB (PostgreSQL): EvidenceDoc, SearchHit                  │
│   - ObjectStore: Raw HTML/JSON snapshots                         │
│   - OpenSearch: Full-text + Vector search index                  │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 基本使用 - 从爬虫输出创建证据

```python
from services.evidence import (
    EvidencePipeline,
    PipelineConfig,
    process_crawler_output,
)

# 配置管道
config = PipelineConfig(
    fetch_detail_pages=True,
    max_detail_fetch_concurrency=10,
    enable_deduplication=True,
    enable_scoring=True,
    enable_versioning=True,
)

pipeline = EvidencePipeline(config=config)

# 处理爬虫输出
result = await pipeline.process_batch(
    crawler_items=crawler_results,  # 来自 CrawlerManager
    query="新冠疫苗安全性",
)

print(f"成功: {result.successful}")
print(f"重复: {result.duplicates}")
print(f"失败: {result.failed}")
```

### 2. 集成 CrawlerManager

```python
from services.layer1_perception.crawler_manager import get_crawler_manager
from services.evidence.integration import collect_evidence_for_investigation

async def investigate_claim(claim: str):
    # 获取爬虫管理器
    crawler_manager = await get_crawler_manager()

    # 收集证据
    result = await collect_evidence_for_investigation(
        query=claim,
        crawler_manager=crawler_manager,
        platforms=["weibo", "zhihu", "bilibili", "xinhua", "people"],
        max_items=100,
    )

    print(f"发现 {result.total_discovered} 条记录")
    print(f"创建 {result.total_evidence} 条证据")
    print(f"按来源分级: {result.by_tier}")

    return result.evidence_docs
```

### 3. 使用 EvidenceCollectionOrchestrator

```python
from services.evidence import (
    EvidenceCollectionOrchestrator,
    EvidenceCollectionConfig,
)

config = EvidenceCollectionConfig(
    platforms=["weibo", "zhihu", "bilibili"],
    max_items_per_platform=50,
    max_total_items=200,
    min_evidence_score=0.3,
    fetch_detail_pages=True,
)

orchestrator = EvidenceCollectionOrchestrator(
    config=config,
    crawler_manager=crawler_manager,
)

result = await orchestrator.collect_evidence(
    query="人工智能发展趋势",
    discovery_mode="search",
)
```

## 数据模型

### SearchHit - 发现记录

```python
@dataclass
class SearchHit:
    hit_id: str              # 唯一标识
    query: str               # 搜索关键词
    entry_url: str           # 发现入口 URL
    hit_url: str             # 目标详情页 URL
    rank: int                # 搜索排名
    hit_title: str           # 搜索结果标题
    hit_snippet: str         # 摘要片段
    platform: str            # 平台标识
    source_domain: str       # 来源域名
    discovery_mode: str      # search/hot/topic/feed
    captured_at: datetime    # 捕获时间
    extra: dict              # 额外信息（热度、互动数等）
    doc_id: str              # 关联的 EvidenceDoc ID
    fetch_status: str        # pending/fetching/success/failed
```

### EvidenceDoc - 证据文档

```python
@dataclass
class EvidenceDoc:
    # 标识
    doc_id: str
    original_url: str
    canonical_url: str

    # 内容
    title: str
    content_text: str
    content_html: str
    media_type: MediaType
    images: List[str]
    videos: List[str]

    # 元数据
    publish_time: datetime
    author: str
    source_org: str
    platform: str

    # 抽取信息
    extraction_method: ExtractionMethod
    extraction_confidence: float

    # 可信度
    source_tier: SourceTier  # S/A/B/C
    evidence_score: float    # 0.0-1.0

    # 版本管理
    version_id: str
    prev_version_id: str
    is_latest: bool
```

## 证据评分

评分公式：
```
evidence_score =
    0.35 * source_tier_score      # 来源层级
  + 0.20 * recency_score          # 时效性
  + 0.20 * corroboration_score    # 独立来源证实
  + 0.15 * extraction_confidence  # 抽取置信度
  + 0.10 * provenance_score       # 来源可追溯性
  - 0.30 * penalty_flags          # 惩罚项
```

### 来源分级

| 层级 | 类型 | 信任分 | 示例 |
|------|------|--------|------|
| S | 权威媒体/官方机构 | 0.95 | 新华社、人民网、央视、gov.cn |
| A | 主流门户/商业媒体 | 0.75 | 澎湃、财新、界面 |
| B | 大型内容平台 | 0.55 | 搜狐、新浪、头条 |
| C | 高噪声社媒 | 0.35 | 微博、知乎、B站、抖音 |

## Search API

### 文本检索

```bash
POST /v1/search
{
    "query": "新冠疫苗安全性",
    "platforms": ["weibo", "zhihu"],
    "source_tiers": ["S", "A"],
    "publish_time_start": "2024-01-01",
    "min_evidence_score": 0.5,
    "size": 20
}
```

### 相似检索

```bash
POST /v1/similar
{
    "doc_id": "doc_weibo_abc123",
    "k": 10
}
```

### OpenSearch DSL 示例

```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"content_text": "关键词"}}
      ],
      "filter": [
        {"term": {"source_tier": "S"}},
        {"range": {"publish_time": {"gte": "now-7d"}}}
      ]
    }
  },
  "highlight": {
    "fields": {"content_text": {}}
  },
  "sort": [
    {"evidence_score": "desc"},
    {"publish_time": "desc"}
  ]
}
```

## 内容抽取优先级

1. **站点模板规则** (置信度: 0.95)
   - CSS/XPath 选择器
   - 平台特定字段映射

2. **JSON-LD 结构化数据** (置信度: 0.80)
   - Schema.org NewsArticle/Article
   - datePublished, author, articleBody

3. **Open Graph 协议** (置信度: 0.70)
   - og:title, og:url, og:description

4. **通用抽取兜底** (置信度: 0.50-0.65)
   - Trafilatura
   - Readability

## 版本管理

```python
from services.evidence import VersionManager, detect_updates

# 检测更新信号
signals = detect_updates(
    content="更正声明：此前报道有误...",
    title="某新闻报道"
)
# signals = {"has_correction_notice": True, ...}

# 获取版本链
manager = VersionManager()
history = manager.get_version_chain(doc_id)
```

## 部署配置

### OpenSearch 索引创建

```python
from services.evidence import get_evidence_index_config
from opensearchpy import OpenSearch

client = OpenSearch(["localhost:9200"])
config = get_evidence_index_config()
client.indices.create(index="evidence", body=config)
```

### IK 中文分词插件

```bash
# 安装 IK 分词器
./bin/opensearch-plugin install analysis-ik
```

### 依赖

```
# requirements.txt 添加
trafilatura>=1.6.0
opensearch-py>=2.0.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

## 集成到 InvestigationEngine

在 `investigation_engine.py` 中使用：

```python
from services.evidence.integration import collect_evidence_for_investigation

class InvestigationOrchestrator:
    async def collect_evidence(self, claim: str):
        # 使用新的证据库管道
        result = await collect_evidence_for_investigation(
            query=claim,
            crawler_manager=self.crawler_manager,
            max_items=self.config.max_evidence_items,
        )

        # 转换为证据卡片格式
        evidence_cards = []
        for doc in result.evidence_docs:
            card = {
                "id": doc.doc_id,
                "url": doc.canonical_url or doc.original_url,
                "title": doc.title,
                "snippet": doc.content_text[:500] if doc.content_text else "",
                "source_tier": doc.source_tier.value,
                "evidence_score": doc.evidence_score,
                "platform": doc.platform,
                "published_at": doc.publish_time.isoformat() if doc.publish_time else None,
            }
            evidence_cards.append(card)

        return evidence_cards
```

## 文件结构

```
aletheia-backend/
├── models/
│   └── evidence.py              # 数据模型定义
├── services/
│   └── evidence/
│       ├── __init__.py          # 模块导出
│       ├── url_normalizer.py    # URL 规范化与去重
│       ├── content_extractor.py # 内容抽取优先级链
│       ├── evidence_scorer.py   # 证据可信度评分
│       ├── version_manager.py   # 版本链管理
│       ├── opensearch_config.py # OpenSearch 索引配置
│       ├── evidence_pipeline.py # 爬虫集成管道
│       └── integration.py       # Investigation 集成
├── config/
│   └── discovery_entries.yaml   # 发现入口配置
├── api/v1/endpoints/
│   └── evidence_search.py       # Search API 端点
└── docs/
    └── EVIDENCE_INTEGRATION_GUIDE.md
```

## 监控与告警

关键指标：
- `evidence_collection_total` - 收集总数
- `evidence_collection_success_rate` - 成功率
- `evidence_deduplication_rate` - 去重率
- `evidence_extraction_confidence_avg` - 平均抽取置信度
- `evidence_score_avg` - 平均证据分数