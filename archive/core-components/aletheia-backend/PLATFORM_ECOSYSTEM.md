# Aletheia 全域多源信息采集系统 - 平台能力矩阵

## 📊 系统概览

**Aletheia v2.0** 现已支持 **7大类别、10+个平台**，覆盖社交媒体、视频平台、问答社区、新闻媒体等全域信息源。

---

## 🌐 平台生态全景图

```
┌────────────────────────────────────────────────────────────────┐
│                      Aletheia 信息采集生态                       │
├────────────────────────────────────────────────────────────────┤
│  📱 社交媒体      │  🎬 视频平台      │  💬 问答社区       │
│  • 微博 (Weibo)   │  • 抖音 (Douyin)  │  • 知乎 (Zhihu)    │
│  • Twitter/X      │  • B站 (Bilibili) │                    │
│  • 小红书 (XHS)   │                   │                    │
├────────────────────────────────────────────────────────────────┤
│  📰 新闻媒体聚合                                                │
│  • 今日头条 (Toutiao)  • 新浪新闻 (Sina)                       │
│  • 腾讯新闻 (QQ News)  • 网易新闻 (NetEase)                    │
└────────────────────────────────────────────────────────────────┘
```

---

## 📋 平台能力矩阵

| 平台 | 类型 | 热搜 | 用户帖子 | 评论 | 搜索 | 媒体类型 | 需要凭证 | 速率限制 |
|-----|------|-----|---------|------|------|---------|---------|---------|
| **微博** | 社交媒体 | ✅ | ✅ | ✅ | ✅ | 图片/视频/文字 | 可选 | 10 req/s |
| **Twitter** | 社交媒体 | ✅ | ✅ | ✅ | ✅ | 图片/视频/文字 | **必需** | 15 req/15min |
| **小红书** | 社交媒体 | ✅ | ✅ | ✅ | ✅ | 图片/视频/文字 | 可选 | 5 req/s |
| **抖音** | 短视频 | ✅ | ✅ | ✅ | ✅ | 视频/图片/文字 | 可选 | 5 req/s |
| **知乎** | 问答社区 | ✅ | ✅ | ✅ | ✅ | 文字/图片 | 推荐 | 10 req/s |
| **B站** | 视频平台 | ✅ | ✅ | ✅ | ✅ | 视频/图片/文字 | 可选 | 10 req/s |
| **新闻聚合** | 新闻媒体 | ✅ | ❌ | ❌ | ✅ | 图片/文字 | 无需 | 10 req/s |

### 功能说明
- **热搜**: 获取平台热门话题/热搜榜
- **用户帖子**: 抓取指定用户发布的内容
- **评论**: 抓取帖子/视频的评论区
- **搜索**: 关键词搜索功能
- **媒体类型**: 支持的内容格式

---

## 🔍 详细平台介绍

### 1. 微博 (Weibo)
**平台属性**: 中国最大社交媒体平台

**功能**:
- ✅ 热搜榜 (实时50条)
- ✅ 用户微博 (包含转发/评论/点赞)
- ✅ 评论抓取 (支持分页)
- ✅ 关键词搜索 (支持时间范围)
- ✅ 图片OCR文字提取
- ✅ 账户年龄计算

**数据字段**:
- 博主信息: 粉丝数、认证状态、账户年龄
- 互动数据: 转发、评论、点赞
- 内容特征: 话题标签、@提及、原创/转发

**适用场景**:
- 舆情监控（热点事件追踪）
- 水军识别（新账户、协同发帖）
- 谣言传播分析

---

### 2. Twitter/X
**平台属性**: 全球最大社交媒体平台之一

**功能**:
- ✅ 热门推文 (综合排序)
- ✅ 用户推文 (时间线)
- ✅ 推文回复 (conversation_id)
- ✅ 关键词搜索 (支持时间窗口)
- ✅ 媒体处理 (图片/视频)
- ✅ 认证标识 (verified)

**数据字段**:
- 用户信息: 粉丝数、认证状态、创建时间
- 互动数据: 点赞、回复、转推、引用
- 内容特征: #话题标签、@提及

**适用场景**:
- 国际舆情监控
- 跨境信息验证
- 海外影响力分析

**限制**:
- **必需API Token** (申请地址: https://developer.twitter.com)
- 免费版: 15请求/15分钟
- 建议使用付费版 (300请求/15分钟)

---

### 3. 小红书 (Xiaohongshu)
**平台属性**: 生活方式分享平台

**功能**:
- ✅ 热搜榜
- ✅ 用户笔记
- ✅ 评论抓取 (支持图片评论)
- ✅ 关键词搜索 (支持排序)
- ✅ 图片OCR框架

**数据字段**:
- 笔记类型: 普通笔记/视频笔记
- 互动数据: 点赞、评论、收藏、分享
- 内容特征: 话题标签

**适用场景**:
- 消费品牌监控
- KOL营销分析
- 产品口碑追踪

---

### 4. 抖音 (Douyin)
**平台属性**: 中国最大短视频平台

**功能**:
- ✅ 热搜榜
- ✅ UP主视频列表
- ✅ 评论抓取
- ✅ 关键词搜索 (支持综合/最新/最热排序)
- ✅ 视频封面/播放地址

**数据字段**:
- 视频信息: 播放量、时长、封面
- 互动数据: 点赞、评论、分享、收藏
- 作者信息: 粉丝数、作品数

**适用场景**:
- 短视频舆情监控
- 品牌传播分析
- 网红影响力评估

**特点**:
- 包含视频播放地址（需额外处理）
- 支持话题标签提取
- 反爬机制较强（需签名）

---

### 5. 知乎 (Zhihu)
**平台属性**: 中国最大问答社区

**功能**:
- ✅ 热榜 (问题/回答/文章)
- ✅ 用户回答列表
- ✅ 评论抓取
- ✅ 综合搜索 (问题/回答/文章)

**数据字段**:
- 内容类型: 问题/回答/文章/想法
- 互动数据: 赞同、评论、收藏
- 作者信息: 粉丝数、专业领域

**适用场景**:
- 专业领域舆情
- 技术话题讨论
- 深度观点分析

**特点**:
- 高质量长文内容
- 专业人士聚集
- 适合深度分析

---

### 6. B站 (Bilibili)
**平台属性**: 中国最大视频弹幕网站

**功能**:
- ✅ 综合热门视频
- ✅ UP主视频列表
- ✅ 评论抓取
- ✅ 关键词搜索 (支持多种排序)

**数据字段**:
- 视频信息: 播放量、时长、封面、分区
- 互动数据: 点赞、投币、收藏、分享、弹幕
- UP主信息: 粉丝数、认证信息

**适用场景**:
- 二次元文化监控
- 游戏/科技话题追踪
- 年轻群体舆情

**特点**:
- 包含投币数（独特互动方式）
- 弹幕数据（需额外API）
- 分区明确（动画/科技/游戏等）

---

### 7. 新闻源聚合器 (News Aggregator)
**平台属性**: 整合4大主流新闻媒体

**支持的新闻源**:
- 📰 今日头条 (Toutiao) - 综合新闻
- 📰 新浪新闻 (Sina) - 传统门户
- 📰 腾讯新闻 (QQ News) - 腾讯系
- 📰 网易新闻 (NetEase) - 网易系

**功能**:
- ✅ 热点新闻聚合（并行抓取4家媒体）
- ✅ 关键词搜索
- ❌ 不支持用户内容
- ❌ 不支持评论

**数据字段**:
- 新闻标题、摘要、URL
- 来源媒体、分类标签
- 发布时间、评论数

**适用场景**:
- 突发事件追踪
- 主流媒体报道对比
- 新闻真实性交叉验证

**特点**:
- 无需凭证
- 并行采集，速度快
- 覆盖主流媒体视角

---

## 🚀 使用指南

### 配置凭证

编辑 `docker/.env` 文件：

```bash
# 微博（可选）
WEIBO_COOKIES=your-cookies-here

# Twitter（必需）
TWITTER_BEARER_TOKEN=your-bearer-token-here

# 小红书（可选）
XHS_COOKIES=your-cookies-here

# 抖音（可选）
DOUYIN_COOKIES=your-cookies-here

# 知乎（推荐）
ZHIHU_COOKIES=your-cookies-here

# B站（可选）
BILIBILI_COOKIES=your-cookies-here

# 新闻聚合器（无需配置）
```

### API调用示例

#### 1. 获取平台列表
```bash
GET /api/v1/multiplatform/platforms
```

响应:
```json
{
  "platforms": [
    {"name": "weibo", "display_name": "微博", "available": true},
    {"name": "douyin", "display_name": "抖音", "available": true},
    {"name": "zhihu", "display_name": "知乎", "available": true},
    {"name": "bilibili", "display_name": "B站", "available": true},
    {"name": "news", "display_name": "新闻聚合", "available": true},
    ...
  ],
  "available_platforms": 7
}
```

#### 2. 多平台热搜
```bash
POST /api/v1/multiplatform/hot-topics
{
  "platforms": ["weibo", "douyin", "zhihu", "news"],
  "limit_per_platform": 20
}
```

#### 3. 跨平台可信度分析
```bash
POST /api/v1/multiplatform/analyze-credibility
{
  "keyword": "某CEO卷款跑路",
  "platforms": ["weibo", "douyin", "zhihu", "bilibili", "news"],
  "limit_per_platform": 50
}
```

响应（示例）:
```json
{
  "credibility_score": 0.25,
  "credibility_level": "LOW",
  "summary": {
    "total_posts": 2340,
    "platform_count": 5,
    "new_account_ratio": 0.62
  },
  "anomalies": [
    {
      "type": "VOLUME_SPIKE",
      "platform": "weibo",
      "z_score": 48.5,
      "description": "微博发帖量异常: Z-score = 48.5"
    },
    {
      "type": "NEW_ACCOUNT_SURGE",
      "ratio": 0.62,
      "description": "新账户占比过高: 62.00%（正常<30%）"
    }
  ],
  "evidence_chain": [...]
}
```

---

## 📊 数据标准化格式

所有平台数据统一为以下格式：

```json
{
  "id": "md5_hash",
  "source_platform": "weibo",
  "original_url": "https://weibo.com/...",
  "content_text": "帖子文本内容",
  "content_type": "TEXT|IMAGE|VIDEO|MIXED",
  "image_urls": ["url1", "url2"],
  "video_url": "video_url",
  "metadata": {
    "timestamp": "2025-02-02T12:00:00Z",
    "author_id": "user123",
    "author_name": "用户名",
    "author_follower_count": 10000,
    "engagement_rate": 0.0234,
    "account_age_days": 365,
    "likes": 1200,
    "comments": 340,
    "shares": 89
  },
  "entities": ["#话题1", "@用户2"],
  "created_at": "2025-02-02T12:00:00Z"
}
```

---

## 🎯 应用场景

### 场景1: 突发事件多源验证
```python
# 某明星出轨传闻验证
result = await analyze_cross_platform_credibility(
    keyword="某明星出轨",
    platforms=["weibo", "douyin", "zhihu", "news"],
    limit_per_platform=100
)

if result['credibility_score'] < 0.3:
    print("⚠️ 高风险: 可能为造谣信息")
    print(f"证据: 新账户占比{result['summary']['new_account_ratio']:.2%}")
```

### 场景2: 品牌舆情监控
```python
# 监控某品牌在各平台的讨论
platforms = ["weibo", "xiaohongshu", "douyin", "bilibili"]
for platform in platforms:
    posts = await search_platform(platform, keyword="某品牌新品")
    sentiment_score = analyze_sentiment(posts)
    print(f"{platform}: 情感分数 {sentiment_score}")
```

### 场景3: 水军识别
```python
# 识别协同水军行为
aggregated = await aggregate_cross_platform_data(
    keyword="某竞品负面",
    platforms=["weibo", "zhihu"],
    limit_per_platform=200
)

if aggregated['summary']['new_account_ratio'] > 0.5:
    if has_time_distribution_anomaly(aggregated):
        print("🚨 检测到协同水军行为")
```

---

## 📈 性能指标

| 操作 | 平均耗时 | 并发性能 |
|-----|---------|---------|
| 单平台热搜 | 1-2秒 | ✅ 支持 |
| 7平台热搜并发 | 2-3秒 | ✅ 支持 |
| 跨平台搜索(5平台x50条) | 8-12秒 | ✅ 支持 |
| 可信度分析(5平台x100条) | 15-25秒 | ✅ 支持 |

**优化建议**:
- 启用Redis缓存（自动，TTL=1小时）
- 限制`limit_per_platform`≤100
- 避免频繁调用同一关键词

---

## 🔧 故障排查

### 问题1: 某平台返回"Not configured"
**原因**: 缺少凭证或凭证无效

**解决**:
1. 检查 `docker/.env` 文件
2. 确认凭证格式正确
3. 重启服务: `docker-compose restart api`

---

### 问题2: 抖音/小红书签名错误
**原因**: 反爬机制升级

**解决**:
- 更新Cookie（重新登录获取）
- 降低请求频率
- 使用代理IP池

---

### 问题3: B站返回412错误
**原因**: 反爬验证触发

**解决**:
- 添加Cookie（登录账号）
- 降低请求频率
- 更换IP地址

---

## 🚧 已知限制

| 平台 | 限制说明 |
|-----|---------|
| **Twitter** | 免费版15 req/15min，需付费提升 |
| **抖音** | 签名算法复杂，可能失效 |
| **小红书** | 反爬较强，建议低频使用 |
| **知乎** | 无Cookie限制较多 |
| **新闻聚合** | 不支持评论和用户内容 |

---

## 📝 开发路线图

### 短期（已完成）
- ✅ 支持7大平台
- ✅ 统一数据格式
- ✅ 跨平台数据融合
- ✅ 异常检测算法

### 中期（规划中）
- [ ] 添加快手、豆瓣
- [ ] 添加Reddit、Facebook
- [ ] 实现分布式爬虫
- [ ] 优化基线算法（真实历史数据）

### 长期（愿景）
- [ ] 图像相似度对比（鉴别PS造假）
- [ ] 视频内容分析（人脸识别、场景识别）
- [ ] 知识图谱（实体关系网络）
- [ ] 情感分析（情绪趋势预测）

---

## 🔗 相关文档

- [快速开始](QUICKSTART.md)
- [多平台爬虫使用指南](MULTIPLATFORM_CRAWLER_GUIDE.md)
- [系统工作流程](SYSTEM_WORKFLOW.md)
- [部署文档](DEPLOYMENT.md)

---

**Aletheia v2.0 - 全域多源信息采集系统**  
**覆盖7大平台类别，10+个主流平台，真相解蔽，多源印证！** 🔍✨
