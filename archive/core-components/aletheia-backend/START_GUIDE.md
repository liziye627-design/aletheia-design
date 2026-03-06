# 🚀 Aletheia项目启动指南

## ⚠️ 第一步：配置Docker Desktop的WSL2集成

### Windows系统操作步骤：

1. **打开Docker Desktop**
   - 在Windows任务栏找到Docker图标并打开

2. **进入设置**
   - 点击右上角齿轮图标⚙️进入Settings

3. **启用WSL2集成**
   - 左侧菜单选择 **Resources** → **WSL Integration**
   - 确保勾选 **"Enable integration with my default WSL distro"**
   - 在下方列表中找到你的Ubuntu发行版，勾选启用
   - 点击 **Apply & Restart** 保存并重启Docker

4. **验证配置**
   ```bash
   # 重新打开WSL终端，运行：
   docker --version
   docker-compose --version
   ```
   如果能看到版本号，说明配置成功！

---

## 🔑 第二步：配置API Keys

### 选项A：使用SiliconFlow（推荐）

1. **获取API Key**
   - 访问：https://cloud.siliconflow.cn/
   - 注册并获取API Key

2. **配置环境变量**
   ```bash
   cd /home/llwxy/aletheia/design/aletheia-backend
   nano docker/.env
   ```

3. **替换以下内容**
   ```bash
   # 将这行：
   SILICONFLOW_API_KEY=your-siliconflow-api-key-here
   
   # 改为你的真实API Key：
   SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxx
   ```

4. **保存退出**
   - 按 `Ctrl + O` 保存
   - 按 `Ctrl + X` 退出

---

## ▶️ 第三步：启动项目

### 方法1：一键启动（推荐）

```bash
cd /home/llwxy/aletheia/design/aletheia-backend
./start.sh
```

启动脚本会自动：
- ✅ 检查Docker环境
- ✅ 验证配置文件
- ✅ 构建Docker镜像
- ✅ 启动所有服务
- ✅ 初始化数据库
- ✅ 显示服务状态

### 方法2：手动启动

```bash
cd /home/llwxy/aletheia/design/aletheia-backend/docker

# 停止旧容器
docker-compose down

# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

---

## 🌐 第四步：访问服务

启动成功后，在浏览器访问：

### 主要服务
- **API文档**: http://localhost:8000/docs
  - Swagger交互式API文档
  - 可以直接测试所有API端点

- **API根路径**: http://localhost:8000
  - 健康检查和基础信息

### 监控服务
- **Grafana**: http://localhost:3001
  - 用户名：admin
  - 密码：admin
  - 实时监控仪表板

- **Prometheus**: http://localhost:9090
  - 指标采集和查询

---

## 🧪 第五步：测试API

### 测试1：健康检查

```bash
curl http://localhost:8000/health
```

期望返回：
```json
{
  "status": "healthy",
  "timestamp": "2026-02-02T22:30:00Z",
  "services": {
    "database": "connected",
    "redis": "connected"
  }
}
```

### 测试2：分析舆情内容

```bash
curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "某品牌新品发布会现场火爆，预订量突破10万！",
    "source_platform": "weibo",
    "metadata": {
      "author_follower_count": 50000,
      "account_age_days": 365,
      "likes": 5000,
      "comments": 1200
    }
  }'
```

### 测试3：多平台热搜

```bash
curl "http://localhost:8000/api/v1/multiplatform/hot-topics?platforms=weibo,douyin&limit=5"
```

### 测试4：图像相似度检测

```bash
curl -X POST "http://localhost:8000/api/v1/vision/compare-images" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url_1": "https://example.com/image1.jpg",
    "image_url_2": "https://example.com/image2.jpg",
    "threshold": 10.0
  }'
```

---

## 📊 查看服务状态

### 查看所有容器

```bash
cd /home/llwxy/aletheia/design/aletheia-backend/docker
docker-compose ps
```

期望看到以下服务：
```
NAME                   STATUS    PORTS
aletheia-api          Up        0.0.0.0:8000->8000/tcp
aletheia-postgres     Up        5432/tcp
aletheia-redis        Up        6379/tcp
aletheia-kafka        Up        9092/tcp
aletheia-grafana      Up        0.0.0.0:3001->3000/tcp
aletheia-prometheus   Up        0.0.0.0:9090->9090/tcp
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看API服务日志
docker-compose logs -f api

# 查看数据库日志
docker-compose logs -f postgres
```

---

## 🔧 常见问题解决

### Q1: Docker命令找不到？

**原因**：WSL2集成未启用

**解决**：
1. 打开Docker Desktop
2. Settings → Resources → WSL Integration
3. 启用你的Ubuntu发行版
4. Apply & Restart
5. 重新打开WSL终端

### Q2: 端口被占用？

**错误信息**：`Bind for 0.0.0.0:8000 failed: port is already allocated`

**解决方案1**：停止占用端口的程序
```bash
# 查找占用8000端口的进程
sudo lsof -i :8000

# 或者
netstat -tunlp | grep 8000

# 杀死进程
sudo kill -9 <PID>
```

**解决方案2**：修改端口
```bash
# 编辑 docker/docker-compose.yml
# 将 8000:8000 改为 8001:8000
```

### Q3: API返回500错误？

**检查步骤**：
```bash
# 1. 查看API日志
docker-compose logs api

# 2. 检查数据库连接
docker exec -it aletheia-postgres psql -U aletheia -d aletheia -c "SELECT 1;"

# 3. 检查Redis连接
docker exec -it aletheia-redis redis-cli -a redis123 PING

# 4. 重启服务
docker-compose restart api
```

### Q4: 数据库初始化失败？

```bash
# 手动初始化数据库
docker exec -it aletheia-api python scripts/init_db.py

# 或者进入容器手动操作
docker exec -it aletheia-api bash
cd /app
python scripts/init_db.py
```

---

## 🛑 停止服务

### 停止所有服务（保留数据）

```bash
cd /home/llwxy/aletheia/design/aletheia-backend/docker
docker-compose stop
```

### 停止并删除容器（保留数据卷）

```bash
docker-compose down
```

### 完全清理（删除所有数据）

```bash
docker-compose down -v  # -v 会删除数据卷
```

---

## 📝 开发模式

### 进入API容器

```bash
docker exec -it aletheia-api bash
```

### 运行Python脚本测试

```bash
docker exec -it aletheia-api python -c "
import asyncio
from services.layer1_perception.crawlers.weibo import WeiboCrawler

async def test():
    crawler = WeiboCrawler()
    topics = await crawler.fetch_hot_topics(limit=3)
    for t in topics:
        print(f'📰 {t[\"content_text\"]}')
    await crawler.close()

asyncio.run(test())
"
```

### 连接数据库

```bash
# PostgreSQL
docker exec -it aletheia-postgres psql -U aletheia -d aletheia

# 常用SQL
\dt                    # 查看所有表
\d intels             # 查看intels表结构
SELECT * FROM intels LIMIT 5;
```

### 连接Redis

```bash
# 进入Redis CLI
docker exec -it aletheia-redis redis-cli -a redis123

# 常用命令
KEYS *                # 查看所有key
GET baseline:xxxx     # 获取某个key的值
```

---

## 🎯 黑客松Demo演示

### 快速演示脚本

```bash
# 1. 显示所有服务状态
docker-compose ps

# 2. 打开API文档
# 浏览器访问: http://localhost:8000/docs

# 3. 测试多平台热搜抓取
curl "http://localhost:8000/api/v1/multiplatform/hot-topics?limit=3" | jq

# 4. 测试真相验证
curl -X POST "http://localhost:8000/api/v1/intel/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "重大消息：某公司被曝光财务造假！",
    "source_platform": "weibo",
    "metadata": {
      "author_follower_count": 100,
      "account_age_days": 7,
      "likes": 10000,
      "comments": 5000
    }
  }' | jq

# 5. 查看Grafana监控
# 浏览器访问: http://localhost:3001 (admin/admin)
```

---

## 📚 相关文档

- **完整README**: `/home/llwxy/aletheia/design/aletheia-backend/README.md`
- **部署指南**: `/home/llwxy/aletheia/design/aletheia-backend/DEPLOYMENT.md`
- **多平台爬虫**: `/home/llwxy/aletheia/design/aletheia-backend/MULTIPLATFORM_CRAWLER_GUIDE.md`
- **完成报告**: `/home/llwxy/aletheia/design/docs/guides/PROJECT_COMPLETION_REPORT.md`

---

## ✅ 检查清单

启动前确认：
- [ ] Docker Desktop已安装并运行
- [ ] WSL2集成已启用
- [ ] API Key已配置（SiliconFlow）
- [ ] 端口8000、3001、9090未被占用

启动后验证：
- [ ] 访问 http://localhost:8000/docs 能看到API文档
- [ ] 访问 http://localhost:8000/health 返回healthy
- [ ] 访问 http://localhost:3001 能看到Grafana
- [ ] `docker-compose ps` 所有服务状态为Up

---

**需要帮助？查看上述常见问题或查看日志排查！** 🚀
