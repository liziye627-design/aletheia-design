# 多平台数据源爬虫系统文档

## 📚 概述

Aletheia多平台数据源系统支持从**微博、Twitter/X、小红书**三个主流社交平台采集数据，并进行跨平台数据融合分析。

---

## 🚀 快速开始

### 1. 配置API凭证

编辑 `docker/.env` 文件，添加以下配置：

```bash
# 微博爬虫配置（可选，无Cookie也可访问公开内容）
WEIBO_COOKIES=your-weibo-cookies-here

# Twitter API配置（必需，需申请开发者账号）
TWITTER_BEARER_TOKEN=your-twitter-bearer-token-here

# 小红书爬虫配置（可选，无Cookie也可访问公开内容）
XHS_COOKIES=your-xiaohongshu-cookies-here
```

### 2. 获取API Token

#### 微博 Cookies
1. 登录 https://weibo.com
2. 打开浏览器开发者工具 (F12)
3. 访问任意微博页面
4. 复制 `Request Headers` 中的 `Cookie` 字段

#### Twitter Bearer Token
1. 访问 https://developer.twitter.com
2. 创建App
3. 在 `Keys and Tokens` 中生成 `Bearer Token`
4. 复制Token值

#### 小红书 Cookies（可选）
1. 登录 https://www.xiaohongshu.com
2. 打开浏览器开发者工具 (F12)
3. 复制 `Cookie` 字段

---

## 📊 支持的平台

| 平台 | 名称 | 功能 | 需要凭证 | 速率限制 |
|-----|------|------|---------|---------|
| weibo | 微博 | 热搜/用户帖子/评论/OCR | 可选 | 10 req/s |
| twitter | Twitter/X | 热门推文/用户推文/回复/搜索 | **必需** | 15 req/15min |
| xiaohongshu | 小红书 | 热搜/笔记/评论/OCR | 可选 | 5 req/s |

---

## 🛠️ API端点

### 1. 获取可用平台列表

```bash
GET /api/v1/multiplatform/platforms
```

**响应示例**:
```json
{
  "success": true,
  "platforms": [
    {
      "name": "weibo",
      "display_name": "微博",
      "available": true,
      "config_status": "✅ Configured"
    },
    {
      "name": "twitter",
      "display_name": "Twitter/X",
      "available": false,
      "config_status": "❌ Not configured"
    }
  ],
  "total_platforms": 3,
  "available_platforms": 1
}
```

---

### 2. 多平台热搜榜

```bash
POST /api/v1/multiplatform/hot-topics
```

**请求体**:
```json
{
  "platforms": ["weibo", "twitter", "xiaohongshu"],
  "limit_per_platform": 20
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "weibo": [
      {
        "id": "abc123...",
        "source_platform": "weibo",
        "content_text": "#某明星事件# 相关内容...",
        "metadata": {
          "timestamp": "2025-02-02T12:00:00Z",
          "likes": 12500,
          "comments": 3400,
          "shares": 8900,
          "engagement_rate": 0.0024
        }
      }
    ],
    "twitter": [...],
    "xiaohongshu": [...]
  },
  "total_topics": 60,
  "platform_count": 3
}
```

---

### 3. 跨平台搜索关键词

```bash
POST /api/v1/multiplatform/search
```

**请求体**:
```json
{
  "keyword": "某CEO卷款跑路",
  "platforms": ["weibo", "twitter"],
  "limit_per_platform": 50
}
```

**响应示例**:
```json
{
  "success": true,
  "keyword": "某CEO卷款跑路",
  "data": {
    "weibo": [
      {
        "id": "def456...",
        "source_platform": "weibo",
        "content_text": "某CEO卷款跑路，受害者已报警...",
        "metadata": {
          "author_name": "用户A",
          "account_age_days": 15,
          "likes": 234,
          "comments": 56
        }
      }
    ],
    "twitter": [...]
  },
  "total_posts": 95,
  "platform_count": 2
}
```

---

### 3.1 Playwright 渲染后抽取（完整页面感知）

```bash
POST /api/v1/multiplatform/playwright-rendered-extract
```

**请求体**:
```json
{
  "url": "https://example.com",
  "critical_selector": "h1",
  "schema": {
    "title": {"selector": "h1", "mode": "text"},
    "links": {"selector": "a", "mode": "attr", "attr": "href", "many": true}
  },
  "api_url_keyword": "api",
  "headless": true
}
```

**响应关键字段**:
```json
{
  "success": true,
  "diagnostics": {
    "playwright_networkidle_reached": true,
    "custom_network_quiet_reached": true,
    "dom_stable": true
  },
  "fields": {
    "title": "Example Domain",
    "links": ["https://iana.org/domains/example"]
  },
  "visible_text": "...",
  "html": "...",
  "api_responses": []
}
```

---

### 4. 跨平台数据聚合分析

```bash
POST /api/v1/multiplatform/aggregate
```

**请求体**:
```json
{
  "keyword": "某CEO卷款跑路",
  "platforms": ["weibo", "twitter", "xiaohongshu"],
  "limit_per_platform": 50
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "keyword": "某CEO卷款跑路",
    "timestamp": "2025-02-02T12:34:56Z",
    "summary": {
      "total_posts": 142,
      "total_engagement": 45600,
      "avg_engagement": 321.13,
      "platform_count": 3,
      "new_account_ratio": 0.42
    },
    "platform_stats": {
      "weibo": {
        "post_count": 87,
        "total_likes": 12300,
        "total_comments": 5600,
        "avg_engagement": 206.32
      },
      "twitter": {...},
      "xiaohongshu": {...}
    },
    "top_entities": [
      ["#某CEO", 56],
      ["@受害者协会", 23],
      ["#卷款跑路", 45]
    ],
    "time_distribution": {
      "0": 5,
      "1": 3,
      "14": 67,
      "15": 45
    },
    "raw_posts": [...]
  }
}
```

---

### 5. 跨平台可信度综合分析 ⭐ **核心功能**

```bash
POST /api/v1/multiplatform/analyze-credibility
```

**请求体**:
```json
{
  "keyword": "某CEO卷款跑路",
  "platforms": ["weibo", "twitter", "xiaohongshu"],
  "limit_per_platform": 50
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "keyword": "某CEO卷款跑路",
    "timestamp": "2025-02-02T12:45:00Z",
    "credibility_score": 0.15,
    "credibility_level": "VERY_LOW",
    "risk_flags": [
      "ABNORMAL_VOLUME_SPIKE",
      "COORDINATED_INAUTHENTIC_BEHAVIOR",
      "HIGH_NEW_ACCOUNT_RATIO"
    ],
    "summary": {
      "total_posts": 1250,
      "platform_count": 3,
      "new_account_ratio": 0.68
    },
    "baseline": {
      "platform_baselines": {
        "weibo": {
          "historical_avg_posts": 50,
          "current_posts": 847,
          "z_score_posts": 53.13
        }
      }
    },
    "anomalies": [
      {
        "type": "VOLUME_SPIKE",
        "platform": "weibo",
        "severity": "HIGH",
        "z_score": 53.13,
        "description": "weibo 发帖量异常: Z-score = 53.13",
        "current_value": 847,
        "baseline_avg": 50
      },
      {
        "type": "NEW_ACCOUNT_SURGE",
        "platform": "all",
        "severity": "HIGH",
        "ratio": 0.68,
        "description": "新账户占比过高: 68.00%（正常<30%）"
      }
    ],
    "evidence_chain": [
      {
        "step": "数据采集",
        "description": "从3个平台采集到1250条相关帖子"
      },
      {
        "step": "weibo基线对比",
        "description": "当前发帖量847条，历史平均50条，Z-score=53.13"
      },
      {
        "step": "异常检测",
        "description": "weibo 发帖量异常: Z-score = 53.13",
        "severity": "HIGH"
      },
      {
        "step": "账户年龄分析",
        "description": "新账户（<30天）占比: 68.00%"
      }
    ]
  }
}
```

**评分规则**:
- **基础分**: 50%
- **扣分项**:
  - 发帖量异常增加: -15%
  - 新账户激增(>30%): -20%
  - 时间分布异常: -10%
- **加分项**:
  - 3个以上平台印证: +15%
  - 高互动质量(>50): +10%

**可信度等级**:
- `VERY_HIGH` (0.8-1.0): 可信度很高
- `HIGH` (0.6-0.8): 可信度高
- `MEDIUM` (0.4-0.6): 可信度中等
- `LOW` (0.2-0.4): 可信度低
- `VERY_LOW` (0.0-0.2): 可信度很低

---

## 🧪 使用示例

### Python示例

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/multiplatform"

# 1. 检查可用平台
response = requests.get(f"{BASE_URL}/platforms")
print(response.json())

# 2. 获取多平台热搜
response = requests.post(f"{BASE_URL}/hot-topics", json={
    "platforms": ["weibo", "twitter"],
    "limit_per_platform": 10
})
print(response.json())

# 3. 跨平台可信度分析
response = requests.post(f"{BASE_URL}/analyze-credibility", json={
    "keyword": "某明星事件",
    "platforms": ["weibo", "twitter", "xiaohongshu"],
    "limit_per_platform": 50
})
result = response.json()
print(f"可信度: {result['data']['credibility_score']:.2%}")
print(f"等级: {result['data']['credibility_level']}")
print(f"风险标签: {result['data']['risk_flags']}")
```

### cURL示例

```bash
# 跨平台可信度分析
curl -X POST "http://localhost:8000/api/v1/multiplatform/analyze-credibility" \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "某CEO卷款跑路",
    "platforms": ["weibo", "twitter"],
    "limit_per_platform": 50
  }'
```

---

## 📈 性能指标

| 操作 | 平均耗时 | 数据量 |
|-----|---------|-------|
| 单平台热搜 | 1-2秒 | 20条 |
| 跨平台搜索 | 3-5秒 | 50条/平台 |
| 可信度分析 | 5-10秒 | 50条/平台 |

**优化建议**:
- 使用Redis缓存（自动启用，TTL=1小时）
- 限制`limit_per_platform`参数（推荐≤50）
- 避免频繁调用同一关键词（利用缓存）

---

## 🔧 故障排查

### 问题1: 平台显示"Not configured"

**原因**: 缺少API凭证或Cookie

**解决**:
1. 检查 `docker/.env` 文件
2. 确保对应平台的凭证已填写
3. 重启服务: `docker-compose restart api`

---

### 问题2: Twitter返回429错误

**原因**: 速率限制（15请求/15分钟）

**解决**:
- 等待15分钟后重试
- 减少`limit_per_platform`参数
- 使用更高级别的Twitter API（需付费）

---

### 问题3: 小红书返回签名错误

**原因**: 反爬虫机制升级

**解决**:
- 更新Cookie（重新登录获取）
- 降低请求频率（当前5 req/s）
- 使用代理IP池（生产环境推荐）

---

## 🚧 限制与注意事项

1. **Twitter API限制**:
   - 免费版: 15请求/15分钟
   - 基础版($100/月): 300请求/15分钟
   - 企业版: 无限制

2. **小红书反爬**:
   - 需定期更新签名算法
   - 建议使用Cookie池
   - 避免短时间大量请求

3. **微博限制**:
   - 无Cookie仅能访问公开内容
   - 需Cookie才能查看完整评论

---

## 📝 更新日志

### v1.1.0 (2025-02-02)
- ✅ 新增Twitter爬虫（660行代码）
- ✅ 新增小红书爬虫（690行代码）
- ✅ 新增爬虫管理器（430行代码）
- ✅ 新增跨平台融合服务（430行代码）
- ✅ 新增5个多平台API端点
- ✅ 新增可信度综合分析功能

### v1.0.0 (2025-01-30)
- ✅ 微博爬虫实现

---

## 🔗 相关文档

- [系统整体架构](../docs/guides/ALETHEIA_PROJECT_OVERVIEW.md)
- [快速开始指南](QUICKSTART.md)
- [部署文档](DEPLOYMENT.md)
- [系统工作流程](SYSTEM_WORKFLOW.md)

---

## 💡 最佳实践

1. **先调用 `/platforms` 检查平台可用性**
2. **使用 `/analyze-credibility` 进行综合分析（推荐）**
3. **结合Layer 3 CoT推理引擎使用（完整可信度评估）**
4. **定期更新API凭证和Cookies**
5. **监控速率限制（Prometheus指标）**

---

**Aletheia多平台数据源系统 - 真相解蔽，多源印证** 🔍✨
