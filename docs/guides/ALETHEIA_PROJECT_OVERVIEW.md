# Aletheia 完整项目总览

## 🎯 项目定位

**Aletheia** (真相解蔽引擎) - 一个基于第一性原理的信息审计系统,通过物理-逻辑-动力学三重验证框架,对海量信息进行真实性评估。

### 核心差异化

| 维度 | 传统舆情系统 | Aletheia |
|------|------------|----------|
| **定位** | 被动收集+情感分类 | 主动质疑+深度验证 |
| **物理验证** | ❌ 无 | ✅ 时空/光影/元数据校验 |
| **逻辑推理** | ❌ 无 | ✅ CoT因果链分析 |
| **熵值计算** | ❌ 无 | ✅ 水军/人工放大检测 |
| **输出** | 情感分类 | 可信度光谱(0-1) |

---

## 🏗️ 系统架构

### 四层架构设计

```
┌─────────────────────────────────────────────────────┐
│  Layer 4: GEO反制行动层                             │
│  功能: JSON-LD生成 | 事实核查报告 | SEO优化         │
│  技术: Jinja2 | Schema.org | SEO预测算法           │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│  Layer 3: 逻辑裁决层 (MCP Protocol)                │
│  功能: CoT推理 | 物理验证 | 逻辑校验 | 熵值计算    │
│  技术: LangChain | GPT-4 | MCP Server             │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│  Layer 2: 动态记忆层                                │
│  功能: 基准线建立 | 异常检测 | 黑名单库            │
│  技术: PostgreSQL | TimescaleDB | Redis            │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│  Layer 1: 全域感知层                                │
│  功能: 多平台爬虫 | OCR/ASR | 实时流处理           │
│  技术: Playwright | PaddleOCR | Kafka              │
└─────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

### 前端 (已完成)

```
aletheia-ui.pen  # Pencil设计文件
├── Desktop
│   ├── IntelSearch - 情报搜索界面
│   ├── Workbench - 分析工作台
│   └── Report - 报告展示
└── Mobile
    ├── Login - 登录
    ├── Feeds - 信息流
    ├── Audit - 审计
    ├── Detail - 详情
    ├── Profile - 个人中心
    ├── History - 历史记录
    └── Settings - 设置
```

### 后端 (本次设计)

```
aletheia-backend/
├── api/                    # API层
│   └── v1/
│       ├── endpoints/      # 端点
│       │   ├── auth.py
│       │   ├── intel.py    ✅ 已创建
│       │   ├── reports.py
│       │   └── feeds.py
│       └── router.py       ✅ 已创建
├── services/               # 业务逻辑层
│   ├── layer1_perception/  # Layer 1
│   │   ├── crawlers/
│   │   └── processors/
│   ├── layer2_memory/      # Layer 2
│   │   ├── baseline.py
│   │   ├── blacklist.py
│   │   └── anomaly_detector.py
│   ├── layer3_reasoning/   # Layer 3
│   │   ├── mcp_server.py
│   │   ├── cot_agent.py
│   │   └── entropy_calculator.py
│   └── layer4_action/      # Layer 4
│       └── report_generator.py
├── models/                 # 数据模型
│   ├── database/
│   │   ├── intel.py        ✅ 已创建
│   │   └── user.py         ✅ 已创建
│   └── schemas/
│       └── intel.py        ✅ 已创建
├── core/                   # 核心配置
│   ├── config.py           ✅ 已创建
│   ├── database.py         ✅ 已创建
│   └── cache.py            ✅ 已创建
├── docker/                 # Docker配置
│   ├── docker-compose.yml  ✅ 已创建
│   ├── Dockerfile          ✅ 已创建
│   └── .env.example        ✅ 已创建
├── main.py                 ✅ 已创建
├── requirements.txt        ✅ 已创建
├── README.md               ✅ 已创建
└── DEPLOYMENT.md           ✅ 已创建
```

---

## 🔗 技术栈整合

### 参考开源项目的借鉴

#### 1. BettaFish - 爬虫架构
- ✅ **采用**: 30+平台适配器模式
- ✅ **采用**: 多协程并发爬取
- ✅ **采用**: 反爬虫策略(UA轮换/代理)
- 📍 **对应模块**: `services/layer1_perception/crawlers/`

#### 2. TrendRadar - MCP协议
- ✅ **采用**: MCP Server架构
- ✅ **采用**: 工具注册机制
- ✅ **采用**: AI分析推送
- 📍 **对应模块**: `services/layer3_reasoning/mcp_server.py`

#### 3. 思通舆情 - 数据处理
- ✅ **采用**: Elasticsearch时序查询
- ✅ **采用**: 舆情基准线建立
- ✅ **采用**: 预警机制
- 📍 **对应模块**: `services/layer2_memory/baseline.py`

---

## 🚀 核心功能实现路径

### Phase 1: MVP (2-3周) ✅ 已设计

**目标**: 打通基础流程,实现文本类逻辑分析

已完成:
- ✅ 四层架构设计
- ✅ 数据库Schema设计
- ✅ API接口规范
- ✅ Docker部署配置

待实现:
- [ ] Layer 3推理引擎核心逻辑
- [ ] 基础爬虫模块(微博/Twitter)
- [ ] 数据库迁移脚本
- [ ] 单元测试

### Phase 2: 多模态引擎 (3-4周)

**目标**: 引入视觉和物理常识校验

- [ ] OCR/ASR集成
- [ ] 物理验证算法(阴影角度/EXIF)
- [ ] Deepfake检测
- [ ] 图片去重

### Phase 3: GEO战略武器 (4周)

**目标**: 实现反制功能

- [ ] JSON-LD生成
- [ ] 事实核查报告模板
- [ ] SEO权重预测
- [ ] 自动发布系统

---

## 📊 数据库设计

### 核心表结构

#### intels (情报主表)
```sql
- id: string (主键)
- source_platform: string (来源平台)
- content_text: text (文本内容)
- credibility_score: float (可信度评分)
- risk_flags: json (风险标签数组)
- physics_verification: json (物理验证结果)
- logic_verification: json (逻辑验证结果)
- entropy_analysis: json (熵值分析)
- created_at, analyzed_at: timestamp
```

#### baselines (基准线表)
```sql
- entity_id: string (实体ID)
- daily_mention_avg: float (日均提及)
- sentiment_distribution: json (情感分布)
- account_type_distribution: json (账号类型)
```

#### water_army_accounts (水军黑名单)
```sql
- account_id: string (账号ID)
- risk_score: int (风险评分 0-100)
- indicators: json (风险指标)
```

---

## 🔌 API接口设计

### 核心端点

#### 1. 情报分析
```
POST /api/v1/intel/analyze
Request:
{
  "content": "待分析文本",
  "source_platform": "weibo",
  "image_urls": ["..."]
}

Response:
{
  "credibility_score": 0.05,
  "risk_flags": ["DEEPFAKE", "WATER_ARMY"],
  "reasoning_chain": [
    "物理层: 图片阴影角度不符",
    "逻辑层: 因果链缺失",
    "动力学层: 信息源熵值0.12"
  ]
}
```

#### 2. 批量分析
```
POST /api/v1/intel/batch
Request:
{
  "items": [...]  # 最多100条
}
```

#### 3. 热点话题
```
GET /api/v1/intel/trending
Response:
{
  "topics": [
    {
      "keyword": "AI",
      "mention_count": 12500,
      "avg_credibility": 0.72
    }
  ]
}
```

---

## 🐳 部署方案

### Docker Compose一键部署

```bash
cd aletheia-backend/docker
cp .env.example .env
# 编辑.env,配置API Key等

docker-compose up -d
# 启动: PostgreSQL, Redis, Kafka, API, Celery, Prometheus, Grafana

# 初始化数据库
docker exec -it aletheia-api alembic upgrade head

# 访问服务
http://localhost:8000/docs  # API文档
http://localhost:3001        # Grafana
```

---

## 📈 性能指标

| 指标 | 目标值 | 测量方式 |
|------|--------|---------|
| API响应时间 | < 200ms (P95) | Prometheus |
| 分析处理时间 | < 5秒 (含AI) | 内部计时 |
| 吞吐量 | > 1000 req/s | 压力测试 |
| 可用性 | 99.9% | Uptime监控 |
| 准确率 | > 90% | 人工对照 |

---

## 🔐 安全设计

### 1. 认证与授权
- JWT Token机制
- 用户角色权限(RBAC)
- API速率限制

### 2. 数据安全
- 密码Bcrypt加密
- 敏感数据加密存储
- SQL注入防护(SQLAlchemy ORM)

### 3. 监控与审计
- Sentry错误追踪
- Prometheus指标监控
- audit_logs表记录所有操作

---

## 📚 下一步行动

### 立即可做

1. **环境准备**
   ```bash
   cd aletheia-backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **启动基础设施**
   ```bash
   cd docker
   docker-compose up -d postgres redis
   ```

3. **实现核心模块**
   - 开始编写`services/layer3_reasoning/cot_agent.py`
   - 实现第一个爬虫`services/layer1_perception/crawlers/weibo.py`

### 分阶段开发

#### Week 1-2: 核心推理引擎
- [ ] MCP Server搭建
- [ ] CoT Prompt编写
- [ ] 基础物理验证

#### Week 3-4: 数据采集层
- [ ] 微博爬虫
- [ ] Twitter爬虫
- [ ] Kafka消息队列

#### Week 5-6: 记忆与分析
- [ ] 基准线建立
- [ ] 异常检测
- [ ] 熵值计算

#### Week 7-8: 前后端联调
- [ ] API完善
- [ ] 前端对接
- [ ] 性能优化

---

## 🙏 致谢

本项目参考了以下优秀开源项目:

- BettaFish - 多平台爬虫架构
- TrendRadar - MCP协议与AI分析
- 思通舆情 - 舆情分析系统设计

---

## 📞 联系方式

- 项目文档: [查看README](/aletheia-backend/README.md)
- 部署指南: [查看DEPLOYMENT](/aletheia-backend/DEPLOYMENT.md)
- 技术栈: Python 3.11 + FastAPI + PostgreSQL + Redis + Kafka
- 许可证: MIT

---

**Built with ❤️ for Truth**
WO
