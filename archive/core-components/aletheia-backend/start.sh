#!/bin/bash

# Aletheia Backend - 一键启动脚本

set -e

echo "🚀 Aletheia Backend - Starting..."

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"

# 进入docker目录
cd docker

# 检查.env文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found, creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}📝 Please edit docker/.env and set your SILICONFLOW_API_KEY${NC}"
    echo -e "${YELLOW}   Then run this script again.${NC}"
    exit 1
fi

# 检查 SiliconFlow API Key
if grep -q "sk-your-siliconflow-api-key" .env; then
    echo -e "${RED}❌ Please set your SILICONFLOW_API_KEY in docker/.env${NC}"
    echo -e "${YELLOW}   Edit the file and replace 'sk-your-siliconflow-api-key' with your real API key.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Configuration found${NC}"

# 停止旧容器
echo -e "${YELLOW}🛑 Stopping old containers...${NC}"
docker-compose down

# 构建镜像
echo -e "${YELLOW}🔨 Building Docker images...${NC}"
docker-compose build

# 启动服务
echo -e "${YELLOW}🚀 Starting services...${NC}"
docker-compose up -d

# 等待数据库启动
echo -e "${YELLOW}⏳ Waiting for database to be ready...${NC}"
sleep 10

# 初始化数据库
echo -e "${YELLOW}🔧 Initializing database...${NC}"
docker exec aletheia-api python scripts/init_db.py

# 显示状态
echo ""
echo -e "${GREEN}✅ Aletheia Backend Started Successfully!${NC}"
echo ""
echo "📊 Service Status:"
docker-compose ps
echo ""
echo "🌐 Access Points:"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - API Root: http://localhost:8000"
echo "   - Grafana: http://localhost:3001 (admin/admin)"
echo "   - Prometheus: http://localhost:9090"
echo ""
echo "📝 View Logs:"
echo "   docker-compose -f docker/docker-compose.yml logs -f"
echo ""
echo "🛑 Stop Services:"
echo "   docker-compose -f docker/docker-compose.yml down"
echo ""
