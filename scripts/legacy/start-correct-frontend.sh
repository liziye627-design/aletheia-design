#!/bin/bash

# Aletheia - 启动正确的前端（WebDashboard）
# 使用 aletheia-mobile 的 Web 版本

set -e

echo "======================================"
echo "  Aletheia 真相洞察引擎 - 启动"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查后端是否运行
echo -e "${BLUE}🔍 检查后端服务...${NC}"
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  后端未运行，正在启动后端...${NC}"
    cd aletheia-backend
    source venv/bin/activate
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > ../backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > ../.backend.pid
    echo -e "${GREEN}✅ 后端已启动 (PID: $BACKEND_PID)${NC}"
    cd ..
    
    # 等待后端启动
    echo -e "${BLUE}⏳ 等待后端就绪...${NC}"
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ 后端已就绪${NC}"
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""
else
    echo -e "${GREEN}✅ 后端已在运行${NC}"
fi

# 启动正确的前端 (aletheia-mobile web)
echo ""
echo -e "${BLUE}🚀 启动 Aletheia WebDashboard (真相洞察引擎)...${NC}"
cd aletheia-mobile

# 检查依赖
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 安装依赖...${NC}"
    npm install
fi

# 启动 Expo Web
echo -e "${GREEN}🌐 启动 Web 界面...${NC}"
nohup npm run web > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../.frontend.pid

cd ..

echo ""
echo "======================================"
echo -e "${GREEN}✅ Aletheia 已启动${NC}"
echo "======================================"
echo ""
echo -e "${BLUE}📊 服务信息:${NC}"
echo -e "  后端 API:  ${GREEN}http://localhost:8000${NC}"
echo -e "  前端界面:  ${GREEN}http://localhost:8081${NC} (Expo Web)"
echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo "  - 查看后端日志: tail -f backend.log"
echo "  - 查看前端日志: tail -f frontend.log"
echo "  - 停止服务: bash scripts/stop-dev.sh"
echo ""
echo -e "${GREEN}🎉 享受使用 Aletheia 真相洞察引擎！${NC}"
echo ""
