# Aletheia Backend - 快速部署指南

## 📦 部署方式

### 方式一: Docker Compose(推荐)

最简单的部署方式,一键启动所有服务。

#### 1. 准备环境

```bash
# 安装Docker和Docker Compose
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose

# macOS
brew install docker docker-compose

# Windows
# 下载 Docker Desktop: https://www.docker.com/products/docker-desktop
```

#### 2. 配置环境变量

```bash
cd aletheia-backend/docker
cp .env.example .env

# 编辑.env文件,修改以下关键配置:
# - SECRET_KEY: 生成一个随机字符串
# - POSTGRES_PASSWORD: 数据库密码
# - REDIS_PASSWORD: Redis密码
# - SILICONFLOW_API_KEY: SiliconFlow API密钥
nano .env
```

#### 3. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 检查服务状态
docker-compose ps
```

#### 4. 初始化数据库

```bash
# 进入API容器
docker exec -it aletheia-api bash

# 运行数据库迁移
alembic upgrade head

# (可选)填充测试数据
python scripts/seed_data.py

# 退出容器
exit
```

#### 5. 访问服务

- API文档: http://localhost:8000/docs
- Grafana: http://localhost:3001 (admin/admin)
- Prometheus: http://localhost:9090

---

### 方式二: 本地开发

适合开发和调试。

#### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 2. 启动基础设施

```bash
# 只启动数据库、Redis、Kafka
cd docker
docker-compose up -d postgres redis kafka
```

#### 3. 配置环境变量

```bash
cp docker/.env.example .env
# 编辑.env,将数据库和Redis的host改为localhost
nano .env
```

#### 4. 初始化数据库

```bash
# 运行迁移
alembic upgrade head

# (可选)填充测试数据
python scripts/seed_data.py
```

#### 5. 启动应用

```bash
# 开发模式(自动重载)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

---

### 方式三: 生产环境部署

#### 使用Nginx反向代理

```nginx
# /etc/nginx/sites-available/aletheia

upstream aletheia_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.aletheia.example.com;

    # 重定向到HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.aletheia.example.com;

    # SSL证书
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 反向代理
    location / {
        proxy_pass http://aletheia_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 静态文件(如果有)
    location /static {
        alias /var/www/aletheia/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 使用Systemd管理服务

```ini
# /etc/systemd/system/aletheia.service

[Unit]
Description=Aletheia Backend API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/aletheia
Environment="PATH=/var/www/aletheia/venv/bin"
ExecStart=/var/www/aletheia/venv/bin/uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --access-log \
    --error-log
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable aletheia
sudo systemctl start aletheia
sudo systemctl status aletheia
```

---

## 🔍 故障排查

### 问题1: 数据库连接失败

```bash
# 检查PostgreSQL是否运行
docker-compose ps postgres

# 查看日志
docker-compose logs postgres

# 测试连接
docker exec -it aletheia-postgres psql -U aletheia -d aletheia
```

### 问题2: Redis连接失败

```bash
# 检查Redis
docker-compose ps redis

# 测试连接
docker exec -it aletheia-redis redis-cli -a your-redis-password ping
```

### 问题3: API启动失败

```bash
# 查看API日志
docker-compose logs api

# 进入容器调试
docker exec -it aletheia-api bash
```

---

## 📊 监控与维护

### 查看性能指标

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001

### 备份数据库

```bash
# 备份PostgreSQL
docker exec aletheia-postgres pg_dump -U aletheia aletheia > backup_$(date +%Y%m%d).sql

# 恢复
docker exec -i aletheia-postgres psql -U aletheia aletheia < backup_20260202.sql
```

### 查看日志

```bash
# 实时日志
docker-compose logs -f

# 特定服务
docker-compose logs -f api

# 保存到文件
docker-compose logs > aletheia_logs.txt
```

---

## 🚀 扩展与优化

### 水平扩展

```bash
# 增加API Worker数量
docker-compose up -d --scale api=3

# 配置负载均衡(Nginx upstream)
```

### 性能优化

1. **启用Redis缓存**
   - 热点数据缓存
   - 分析结果缓存

2. **数据库优化**
   - 创建索引
   - 查询优化
   - 连接池配置

3. **异步任务**
   - 使用Celery处理耗时任务
   - Kafka消息队列

---

## 📞 获取帮助

- 文档: `docs/guides/INTEGRATION_GUIDE.md`
- 问题反馈: 通过项目维护群/工单
- 邮箱: support@aletheia.example.com
