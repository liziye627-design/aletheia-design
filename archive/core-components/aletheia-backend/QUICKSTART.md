# Aletheia Backend - 快速启动指南

## 🎯 一键启动

### 前置要求
- Docker 20.10+
- Docker Compose 2.0+
- SiliconFlow API Key

### 快速开始

```bash
# 1. 进入项目目录
cd /home/llwxy/aletheia/design/aletheia-backend

# 2. 编辑环境变量
nano docker/.env
# 修改SILICONFLOW_API_KEY为你的真实API Key

# 3. 一键启动
./start.sh
```

就这么简单! 🎉

## 📊 访问服务

启动成功后,你可以访问:

- **API文档**: http://localhost:8000/docs
- **API根路径**: http://localhost:8000
- **Grafana监控**: http://localhost:3001 (用户名:admin 密码:admin)
- **Prometheus**: http://localhost:9090

## 🧪 测试API

### 1. 测试分析接口

```bash
curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "某CEO卷款跑路,受害者已报警",
    "source_platform": "weibo",
    "metadata": {
      "author_follower_count": 50000,
      "account_age_days": 10
    }
  }'
```

### 2. 查看微博热搜

可以在API容器中测试微博爬虫:

```bash
docker exec -it aletheia-api python -c "
import asyncio
from services.layer1_perception.crawlers.weibo import WeiboCrawler

async def test():
    crawler = WeiboCrawler()
    hot_topics = await crawler.fetch_hot_topics(limit=5)
    for topic in hot_topics:
        print(f'📰 {topic[\"content_text\"]}')
    await crawler.close()

asyncio.run(test())
"
```

## 📁 项目结构

```
aletheia-backend/
├── services/
│   ├── layer1_perception/
│   │   └── crawlers/
│   │       ├── base.py          ✅ 爬虫基类
│   │       └── weibo.py         ✅ 微博爬虫
│   ├── layer2_memory/
│   │   ├── baseline.py          ✅ 基准线建立
│   │   └── anomaly_detector.py  ✅ 异常检测
│   └── layer3_reasoning/
│       └── cot_agent.py         ✅ CoT推理引擎
├── docker/
│   ├── docker-compose.yml       ✅ Docker配置
│   └── .env                     ✅ 环境变量
├── start.sh                     ✅ 一键启动脚本
└── main.py                      ✅ 主应用
```

## 🔧 常见问题

### Q1: 启动失败怎么办?

```bash
# 查看日志
docker-compose -f docker/docker-compose.yml logs

# 重启服务
docker-compose -f docker/docker-compose.yml restart
```

### Q2: 如何查看数据库?

```bash
# 连接PostgreSQL
docker exec -it aletheia-postgres psql -U aletheia -d aletheia

# 查看表
\dt

# 查询数据
SELECT * FROM intels LIMIT 10;
```

### Q3: 如何查看Redis缓存?

```bash
# 连接Redis
docker exec -it aletheia-redis redis-cli -a redis123

# 查看所有key
KEYS *

# 查看某个key
GET cot_analysis:xxxxx
```

### Q4: API返回401/403错误?

目前API还没有实现认证,所有端点都是开放的。如果遇到认证错误,请检查:
- Docker容器是否正常运行
- 环境变量是否正确配置

## 🚀 下一步

1. **配置微博Cookie**  
   如果需要抓取更多微博数据,在`.env`中配置`WEIBO_COOKIES`

2. **添加更多平台爬虫**  
   参考`services/layer1_perception/crawlers/weibo.py`,实现Twitter、小红书等

3. **优化CoT提示词**  
   编辑`services/layer3_reasoning/cot_agent.py`中的`SYSTEM_PROMPT`

4. **对接前端UI**  
   使用`aletheia-ui.pen`中的设计实现前端界面

## 📞 获取帮助

- 查看完整文档: [README.md](README.md)
- 部署指南: [DEPLOYMENT.md](DEPLOYMENT.md)
- 项目总览: [ALETHEIA_PROJECT_OVERVIEW.md](../docs/guides/ALETHEIA_PROJECT_OVERVIEW.md)

---

**Built with ❤️ for Truth**
