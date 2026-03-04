#!/bin/bash

# =====================================================
# Aletheia Truth Engine - 启动脚本 (优化版本)
# 基于最新的系统架构和Bot检测功能
# =====================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="${SCRIPT_DIR}/aletheia-backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
MOBILE_DIR="${SCRIPT_DIR}/aletheia-mobile"

# 默认端口
BACKEND_PORT=8000
FRONTEND_PORT=5173

# 显示横幅
show_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                                                           ║"
    echo "║     █████╗ ██╗     ███████╗████████╗██╗  ██╗███████╗██╗  ██╗    ║"
    echo "║    ██╔══██╗██║     ██╔════╝╚══██╔══╝██║  ██║██╔════╝██║  ██║    ║"
    echo "║    ███████║██║     █████╗     ██║   ███████║█████╗  ██║  ██║    ║"
    echo "║    ██╔══██║██║     ██╔══╝     ██║   ██╔══██║██╔══╝  ██║  ██║    ║"
    echo "║    ██║  ██║███████╗███████╗   ██║   ██║  ██║███████╗██║  ██║    ║"
    echo "║    ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝    ║"
    echo "║                                                           ║"
    echo "║              真相解蔽引擎 - Truth Engine                  ║"
    echo "║         基于第一性原理的信息审计系统 v2.0                 ║"
    echo "║                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查端口是否被占用
port_busy() {
    local port="$1"
    if command_exists ss; then
        ss -ltn 2>/dev/null | grep -q ":${port} " && return 0 || return 1
    elif command_exists lsof; then
        lsof -i ":${port}" >/dev/null 2>&1 && return 0 || return 1
    else
        netstat -an 2>/dev/null | grep -q ":${port} " && return 0 || return 1
    fi
}

# 查找可用端口
find_available_port() {
    local start_port=$1
    local port=$start_port
    while port_busy $port; do
        port=$((port + 1))
        if [ $port -gt $((start_port + 100)) ]; then
            echo -e "${RED}无法找到可用端口${NC}"
            exit 1
        fi
    done
    echo $port
}

# 检查Python环境
check_python() {
    echo -e "${YELLOW}检查Python环境...${NC}"
    
    if ! command_exists python3; then
        echo -e "${RED}错误: 未找到Python 3${NC}"
        exit 1
    fi
    
    local python_version=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python版本: $python_version${NC}"
}

# 检查Node.js环境
check_node() {
    echo -e "${YELLOW}检查Node.js环境...${NC}"
    
    if ! command_exists node; then
        echo -e "${RED}错误: 未找到Node.js${NC}"
        exit 1
    fi
    
    local node_version=$(node --version)
    echo -e "${GREEN}✓ Node.js版本: $node_version${NC}"
}

network_preflight() {
    echo -e "${YELLOW}执行网络预检（DNS/代理）...${NC}"

    local proxy_summary="${HTTP_PROXY:-${http_proxy:-}}|${HTTPS_PROXY:-${https_proxy:-}}|${ALL_PROXY:-${all_proxy:-}}"
    if [ -n "${proxy_summary//|/}" ]; then
        echo -e "${YELLOW}检测到代理变量:${NC}"
        echo "  HTTP_PROXY=${HTTP_PROXY:-${http_proxy:-<empty>}}"
        echo "  HTTPS_PROXY=${HTTPS_PROXY:-${https_proxy:-<empty>}}"
        echo "  ALL_PROXY=${ALL_PROXY:-${all_proxy:-<empty>}}"
        if echo "$proxy_summary" | grep -Eq "127\.0\.0\.1|localhost"; then
            echo -e "${YELLOW}⚠ 使用本地代理时请确认代理已启动，否则会导致爬虫普遍超时${NC}"
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
        echo -e "${YELLOW}⚠ 网络预检未全部通过：系统将继续启动并使用可解释降级。${NC}"
        echo -e "${YELLOW}  建议执行：unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy${NC}"
    else
        echo -e "${GREEN}✓ 网络预检通过${NC}"
    fi
}

# 初始化后端
init_backend() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}初始化后端环境${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    cd "$BACKEND_DIR"
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}创建Python虚拟环境...${NC}"
        python3 -m venv venv
        echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 安装依赖
    echo -e "${YELLOW}安装Python依赖...${NC}"
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo -e "${GREEN}✓ 依赖安装完成${NC}"
    
    # 初始化数据库
    if [ ! -f "aletheia.db" ]; then
        echo -e "${YELLOW}初始化数据库...${NC}"
        python scripts/init_db.py
        echo -e "${GREEN}✓ 数据库初始化完成${NC}"
    fi
    
    # 运行数据库迁移
    echo -e "${YELLOW}运行数据库迁移...${NC}"
    alembic upgrade head
    echo -e "${GREEN}✓ 数据库迁移完成${NC}"
}

# 启动后端服务
start_backend() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}启动后端服务${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    cd "$BACKEND_DIR"
    source venv/bin/activate
    
    # 检查端口
    if port_busy $BACKEND_PORT; then
        echo -e "${YELLOW}端口 $BACKEND_PORT 已被占用,查找可用端口...${NC}"
        BACKEND_PORT=$(find_available_port $BACKEND_PORT)
        echo -e "${GREEN}使用端口: $BACKEND_PORT${NC}"
    fi
    
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}后端服务启动中...${NC}"
    echo -e "${GREEN}地址: http://localhost:$BACKEND_PORT${NC}"
    echo -e "${GREEN}API文档: http://localhost:$BACKEND_PORT/docs${NC}"
    echo -e "${GREEN}健康检查: http://localhost:$BACKEND_PORT/health${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # 启动uvicorn
    uvicorn main:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --reload \
        --log-level info &
    
    BACKEND_PID=$!
    echo -e "${GREEN}✓ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
    
    # 等待服务启动
    echo -e "${YELLOW}等待后端服务就绪...${NC}"
    sleep 3
    
    # 检查服务是否正常
    if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null; then
        echo -e "${GREEN}✓ 后端服务运行正常${NC}"
    else
        echo -e "${RED}✗ 后端服务启动失败${NC}"
        exit 1
    fi
}

# 初始化前端
init_frontend() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}初始化前端环境${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${YELLOW}前端目录不存在,跳过前端启动${NC}"
        return 1
    fi
    
    cd "$FRONTEND_DIR"
    
    # 安装依赖
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}安装前端依赖...${NC}"
        npm install
        echo -e "${GREEN}✓ 依赖安装完成${NC}"
    fi
    
    return 0
}

# 启动前端服务
start_frontend() {
    if ! init_frontend; then
        return
    fi
    
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}启动前端服务${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    cd "$FRONTEND_DIR"
    
    # 检查端口
    if port_busy $FRONTEND_PORT; then
        echo -e "${YELLOW}端口 $FRONTEND_PORT 已被占用,查找可用端口...${NC}"
        FRONTEND_PORT=$(find_available_port $FRONTEND_PORT)
        echo -e "${GREEN}使用端口: $FRONTEND_PORT${NC}"
    fi
    
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}前端服务启动中...${NC}"
    echo -e "${GREEN}地址: http://localhost:$FRONTEND_PORT${NC}"
    echo -e "${GREEN}后端API: http://localhost:$BACKEND_PORT/api/v1${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # 设置环境变量并启动
    VITE_API_BASE_URL="http://localhost:$BACKEND_PORT/api/v1" \
    npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT &
    
    FRONTEND_PID=$!
    echo -e "${GREEN}✓ 前端服务已启动 (PID: $FRONTEND_PID)${NC}"
}

# 显示系统信息
show_system_info() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}系统信息${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}架构层次:${NC}"
    echo -e "  • Layer 1 (感知层): 多平台数据采集 + Bot检测"
    echo -e "  • Layer 2 (记忆层): 数据存储 + 缓存 + 索引"
    echo -e "  • Layer 3 (推理层): LLM分析 + 假新闻检测"
    echo -e "  • Layer 4 (反制层): 对抗检测 + 规避策略"
    echo ""
    echo -e "${GREEN}核心功能:${NC}"
    echo -e "  ✓ 36个平台数据采集"
    echo -e "  ✓ Bot/水军检测系统"
    echo -e "  ✓ CIB协同造假检测"
    echo -e "  ✓ 假新闻ML模型集成"
    echo -e "  ✓ 多Agent智能协作"
    echo -e "  ✓ 实时数据分析"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}正在关闭服务...${NC}"
    
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        echo -e "${GREEN}✓ 后端服务已关闭${NC}"
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}✓ 前端服务已关闭${NC}"
    fi
    
    echo -e "${CYAN}再见! 👋${NC}"
}

# 设置清理陷阱
trap cleanup EXIT INT TERM

# 主函数
main() {
    show_banner
    
    # 检查环境
    check_python
    check_node
    network_preflight
    
    # 根据参数决定启动什么
    case "${1:-all}" in
        backend)
            init_backend
            start_backend
            show_system_info
            echo -e "\n${GREEN}按 Ctrl+C 停止服务${NC}"
            wait
            ;;
        frontend)
            start_frontend
            echo -e "\n${GREEN}按 Ctrl+C 停止服务${NC}"
            wait
            ;;
        all)
            init_backend
            start_backend
            sleep 2
            start_frontend
            show_system_info
            echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${GREEN}所有服务已启动! 按 Ctrl+C 停止服务${NC}"
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            wait
            ;;
        init)
            init_backend
            init_frontend
            echo -e "${GREEN}✓ 初始化完成${NC}"
            ;;
        *)
            echo "用法: $0 {backend|frontend|all|init}"
            echo ""
            echo "  backend   - 仅启动后端服务"
            echo "  frontend  - 仅启动前端服务"
            echo "  all       - 启动所有服务 (默认)"
            echo "  init      - 仅初始化环境,不启动服务"
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
