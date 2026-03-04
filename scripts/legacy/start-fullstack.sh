#!/bin/bash

echo "=========================================="
echo "  🚀 Aletheia 全栈启动脚本"
echo "=========================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

network_preflight() {
    echo -e "\n${YELLOW}🌐 网络预检（DNS/代理）...${NC}"
    local proxy_summary="${HTTP_PROXY:-${http_proxy:-}}|${HTTPS_PROXY:-${https_proxy:-}}|${ALL_PROXY:-${all_proxy:-}}"
    if [ -n "${proxy_summary//|/}" ]; then
        echo -e "${YELLOW}检测到代理变量: HTTP_PROXY/HTTPS_PROXY/ALL_PROXY${NC}"
        echo "  HTTP_PROXY=${HTTP_PROXY:-${http_proxy:-<empty>}}"
        echo "  HTTPS_PROXY=${HTTPS_PROXY:-${https_proxy:-<empty>}}"
        echo "  ALL_PROXY=${ALL_PROXY:-${all_proxy:-<empty>}}"
        if echo "$proxy_summary" | grep -Eq "127\.0\.0\.1|localhost"; then
            echo -e "${YELLOW}⚠ 本地代理可能导致爬虫无数据，请确认代理端口已启动${NC}"
        fi
    fi

    local dns_ok=1
    for host in duckduckgo.com feeds.bbci.co.uk api.siliconflow.cn; do
        if python3 -c "import socket; socket.gethostbyname('${host}')" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ DNS OK: ${host}${NC}"
        else
            dns_ok=0
            echo -e "${RED}✗ DNS 失败: ${host}${NC}"
        fi
    done

    local http_ok=1
    if curl -sS -m 6 -I https://feeds.bbci.co.uk/news/rss.xml >/dev/null 2>&1; then
        echo -e "${GREEN}✓ HTTP OK: feeds.bbci.co.uk${NC}"
    else
        http_ok=0
        echo -e "${RED}✗ HTTP 失败: feeds.bbci.co.uk${NC}"
    fi
    if curl -sS -m 6 -I https://api.siliconflow.cn/v1/models >/dev/null 2>&1; then
        echo -e "${GREEN}✓ HTTP OK: api.siliconflow.cn${NC}"
    else
        http_ok=0
        echo -e "${RED}✗ HTTP 失败: api.siliconflow.cn${NC}"
    fi

    if [ "$dns_ok" -eq 0 ] || [ "$http_ok" -eq 0 ]; then
        echo -e "${YELLOW}⚠ 网络预检未全部通过：系统会以“可解释降级”运行。${NC}"
        echo -e "${YELLOW}  建议：清理无效代理变量后重试，例如：unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy${NC}"
    else
        echo -e "${GREEN}✅ 网络预检通过${NC}"
    fi
}

network_preflight

# 检查后端是否已运行
echo -e "\n${YELLOW}📡 检查后端状态...${NC}"
backend_running=$(curl -s http://localhost:8000/health 2>/dev/null | grep -o "healthy" || echo "")

if [ "$backend_running" = "healthy" ]; then
    echo -e "${GREEN}✅ 后端已在运行 (http://localhost:8000)${NC}"
else
    echo -e "${YELLOW}⚠️  后端未运行，正在启动...${NC}"
    cd aletheia-backend
    bash run-server.sh &
    BACKEND_PID=$!
    cd ..
    
    # 等待后端启动
    echo "等待后端启动..."
    for i in {1..30}; do
        sleep 1
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ 后端启动成功！${NC}"
            break
        fi
        echo -n "."
    done
fi

# 检查前端是否已运行
echo -e "\n${YELLOW}🎨 检查前端状态...${NC}"
frontend_running=$(curl -s http://localhost:5173 2>/dev/null | grep -o "html" || echo "")

if [ -n "$frontend_running" ]; then
    echo -e "${GREEN}✅ 前端已在运行 (http://localhost:5173)${NC}"
else
    echo -e "${YELLOW}⚠️  前端未运行，正在启动...${NC}"
    cd frontend
    
    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo "📦 安装前端依赖..."
        npm install
    fi
    
    # 启动前端开发服务器
    npm run dev &
    FRONTEND_PID=$!
    cd ..
    
    echo -e "${GREEN}✅ 前端启动中...${NC}"
fi

# 显示服务信息
echo -e "\n=========================================="
echo -e "  ${GREEN}🎉 Aletheia 全栈服务已启动${NC}"
echo "=========================================="
echo ""
echo "📊 服务地址:"
echo "  • 前端 (React):     http://localhost:5173"
echo "  • 后端 (FastAPI):   http://localhost:8000"
echo "  • API 文档:         http://localhost:8000/docs"
echo "  • 健康检查:         http://localhost:8000/health"
echo ""
echo "🔧 功能状态:"
echo "  ✓ 增强版情报分析 (SiliconFlow API)"
echo "  ✓ Bot 检测系统"
echo "  ✓ 情报查询和搜索"
echo "  ✓ 热门话题统计"
echo "  ⚠ Redis 缓存 (未启用，已降级)"
echo ""
echo "📝 日志查看:"
echo "  • 后端日志: tail -f aletheia-backend/logs/*.log"
echo "  • 前端日志: 查看终端输出"
echo ""
echo "🛑 停止服务:"
echo "  • Ctrl+C 或运行: pkill -f 'vite|uvicorn'"
echo ""
echo "=========================================="
echo -e "${GREEN}✨ 准备就绪！请在浏览器中访问前端地址${NC}"
echo "=========================================="

# 保持脚本运行
wait
