# Aletheia Backend - 真相解蔽引擎后端系统

## 📋 项目概述

Aletheia是一个基于第一性原理的信息审计引擎,通过物理-逻辑-动力学三重验证框架,对信息进行真实性评估。

## 🏗️ 技术栈

### 核心框架
- **Python 3.11+**
- **FastAPI** - 高性能异步Web框架
- **SQLAlchemy 2.0** - ORM框架
- **Pydantic V2** - 数据验证

### 数据库
- **PostgreSQL 15+** - 主数据库
- **Redis 7+** - 缓存与消息队列
- **TimescaleDB** - 时序数据存储
- **Qdrant** - 向量数据库(用于语义搜索)

### 消息队列
- **Apache Kafka** - 实时数据流处理
- **Celery** - 异步任务队列

### AI/ML框架
- **LangChain** - LLM应用框架
- **SiliconFlow** - 推理引擎
- **PaddleOCR** - 中文OCR识别
- **MediaPipe** - 视觉处理

### 监控与部署
- **Docker + Docker Compose**
- **Prometheus + Grafana** - 监控
- **Sentry** - 错误追踪
- **Nginx** - 反向代理

## 📁 项目结构

```
aletheia-backend/
├── api/                    # API层
│   ├── v1/                 # API版本1
│   │   ├── endpoints/      # 端点
│   │   │   ├── auth.py
│   │   │   ├── intel.py
│   │   │   ├── audit.py
│   │   │   ├── reports.py
│   │   │   └── feeds.py
│   │   ├── deps.py         # 依赖注入
│   │   └── router.py       # 路由聚合
│   └── graphql/            # GraphQL接口(可选)
├── services/               # 业务逻辑层
│   ├── layer1_perception/  # Layer 1: 全域感知
│   │   ├── crawlers/
│   │   │   ├── weibo.py
│   │   │   ├── twitter.py
│   │   │   └── base.py
│   │   ├── processors/
│   │   │   ├── ocr.py
│   │   │   ├── asr.py
│   │   │   └── vision.py
│   │   └── kafka_producer.py
│   ├── layer2_memory/      # Layer 2: 动态记忆
│   │   ├── baseline.py
│   │   ├── blacklist.py
│   │   └── anomaly_detector.py
│   ├── layer3_reasoning/   # Layer 3: 逻辑裁决
│   │   ├── mcp_server.py
│   │   ├── cot_agent.py
│   │   ├── physics_verifier.py
│   │   └── entropy_calculator.py
│   └── layer4_action/      # Layer 4: GEO反制
│       ├── report_generator.py
│       ├── jsonld_builder.py
│       └── seo_optimizer.py
├── models/                 # 数据模型
│   ├── database/           # 数据库模型
│   │   ├── user.py
│   │   ├── intel.py
│   │   ├── audit.py
│   │   └── report.py
│   └── schemas/            # Pydantic模型
│       ├── auth.py
│       ├── intel.py
│       └── report.py
├── core/                   # 核心配置
│   ├── config.py           # 配置管理
│   ├── security.py         # 安全相关
│   ├── database.py         # 数据库连接
│   └── cache.py            # 缓存管理
├── utils/                  # 工具函数
│   ├── logging.py
│   ├── exceptions.py
│   └── helpers.py
├── tests/                  # 测试
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── scripts/                # 脚本
│   ├── init_db.py
│   └── seed_data.py
├── docker/                 # Docker配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── alembic/                # 数据库迁移
├── main.py                 # 应用入口
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 进入项目目录
cd aletheia-backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp docker/.env.example .env
# 编辑.env文件,配置数据库、Redis、SiliconFlow API Key等
```

### 3. 启动基础设施

```bash
# 使用Docker Compose启动数据库、Redis、Kafka
cd docker
docker-compose up -d postgres redis kafka
```

### 4. 初始化数据库

```bash
# 运行数据库迁移
alembic upgrade head

# (可选)填充测试数据
python scripts/seed_data.py
```

### 5. 启动服务

```bash
# 开发模式
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

### 6. 访问API文档

打开浏览器访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📚 核心功能模块

### Layer 1: 全域感知层
- **多平台爬虫**: 微博、Twitter、小红书等30+平台
- **多模态处理**: OCR、ASR、视频关键帧提取
- **实时流处理**: Kafka消息队列

### Layer 2: 动态记忆层
- **基准线建立**: 为每个实体建立"正常状态"
- **异常检测**: Z-score检验、分布对比
- **黑名单库**: 水军账号指纹识别

### Layer 3: 逻辑裁决层
- **MCP协议服务器**: 兼容Claude、ChatGPT等AI助手
- **CoT推理链**: 物理-逻辑-动力学三重验证
- **熵值计算**: 信息源多样性分析

### Layer 4: GEO反制层
- **报告生成**: 自动生成事实核查报告
- **JSON-LD**: Schema.org格式结构化数据
- **SEO优化**: 搜索引擎权重预测

## 🔧 配置说明

### 环境变量

```env
# 应用配置
APP_NAME=Aletheia
APP_VERSION=1.0.0
DEBUG=False

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/aletheia
REDIS_URL=redis://localhost:6379/0

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# AI服务
SILICONFLOW_API_KEY=sk-xxx
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3

# OCR/ASR
PADDLE_OCR_MODEL_DIR=/path/to/models
```

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定模块
pytest tests/unit/services/layer3_reasoning/

# 生成覆盖率报告
pytest --cov=. --cov-report=html
```

## 📊 监控与性能

### 性能指标
- API响应时间: < 200ms (P95)
- 分析处理时间: < 5秒 (含AI推理)
- 吞吐量: > 1000 req/s
- 可用性: 99.9%

### 监控端点
- `/health` - 健康检查
- `/metrics` - Prometheus指标
- `/api/v1/stats` - 系统统计

## 🐳 Docker部署

```bash
# 构建镜像
docker build -t aletheia-backend:latest .

# 使用Docker Compose启动完整服务
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

## 📄 API文档

### 认证
- `POST /api/v1/auth/login` - 用户登录
- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/refresh` - 刷新Token

### 情报分析
- `POST /api/v1/intel/analyze` - 分析单条信息
- `GET /api/v1/intel/trending` - 获取热点话题
- `POST /api/v1/intel/batch` - 批量分析

### 审计报告
- `GET /api/v1/reports` - 获取报告列表
- `GET /api/v1/reports/{id}` - 获取报告详情
- `POST /api/v1/reports/generate` - 生成新报告

### 数据流
- `GET /api/v1/feeds` - 获取实时数据流
- `POST /api/v1/feeds/filter` - 设置过滤条件

## 🤝 贡献指南

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 📝 开发规范

- 遵循PEP 8代码风格
- 使用Black进行代码格式化
- 使用MyPy进行类型检查
- 编写单元测试(覆盖率 > 80%)
- 使用Conventional Commits规范提交信息

## 📜 许可证

本项目采用MIT许可证 - 详见 [LICENSE](LICENSE) 文件

## 📮 联系方式

- 项目主页: 内部部署入口
- 问题反馈: 通过项目维护群/工单
- 邮箱: support@aletheia.example.com

## 🙏 致谢

本项目参考了以下开源项目:
- BettaFish - 多平台爬虫
- TrendRadar - 热点监测
- 思通舆情 - 舆情分析

---

**Built with ❤️ for Truth**
