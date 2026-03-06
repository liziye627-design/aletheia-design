#!/bin/bash

# =====================================================
# Aletheia 开发环境启动脚本
# 用途: 启动前后端服务并监控健康状态
# =====================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 运行时目录（统一收纳日志与PID）
RUNTIME_DIR="$PROJECT_ROOT/runtime"
RUNTIME_LOG_DIR="$RUNTIME_DIR/logs"
RUNTIME_PID_DIR="$RUNTIME_DIR/pids"
mkdir -p "$RUNTIME_LOG_DIR" "$RUNTIME_PID_DIR"

# PID和日志文件
BACKEND_PID_FILE="$RUNTIME_PID_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_PID_DIR/frontend.pid"
BACKEND_LOG_FILE="$RUNTIME_LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$RUNTIME_LOG_DIR/frontend.log"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Aletheia 开发环境启动${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =====================================================
# 1. 检查依赖
# =====================================================
echo -e "${YELLOW}🔍 检查系统依赖...${NC}"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 Node.js${NC}"
    echo -e "${YELLOW}💡 请安装 Node.js 18+ : https://nodejs.org/${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "${GREEN}✅ Node.js: $NODE_VERSION${NC}"

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 npm${NC}"
    exit 1
fi
NPM_VERSION=$(npm --version)
echo -e "${GREEN}✅ npm: $NPM_VERSION${NC}"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 Python3${NC}"
    echo -e "${YELLOW}💡 请安装 Python 3.10+ : https://www.python.org/${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ Python: $PYTHON_VERSION${NC}"

echo ""

# =====================================================
# 2. 检查环境配置
# =====================================================
echo -e "${YELLOW}📝 检查环境配置...${NC}"

FRONTEND_ENV="$PROJECT_ROOT/frontend/.env"
BACKEND_ENV="$PROJECT_ROOT/aletheia-backend/.env"

if [ ! -f "$FRONTEND_ENV" ]; then
    echo -e "${RED}❌ 错误: 前端 .env 文件不存在${NC}"
    echo -e "${YELLOW}💡 请运行: ./scripts/setup-env.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 前端 .env 文件存在${NC}"

if [ ! -f "$BACKEND_ENV" ]; then
    echo -e "${RED}❌ 错误: 后端 .env 文件不存在${NC}"
    echo -e "${YELLOW}💡 请运行: ./scripts/setup-env.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 后端 .env 文件存在${NC}"

echo ""

# =====================================================
# 2.1 修正非法 DEBUG 环境变量（避免 pydantic 报错）
# =====================================================
if [ -n "${DEBUG:-}" ]; then
    DEBUG_LOWER="$(echo "$DEBUG" | tr '[:upper:]' '[:lower:]')"
    case "$DEBUG_LOWER" in
        true|false|1|0|yes|no)
            # ok
            ;;
        *)
            echo -e "${YELLOW}⚠️  检测到 DEBUG=$DEBUG（非布尔值），已忽略该环境变量，使用 .env 配置${NC}"
            unset DEBUG
            ;;
    esac
fi

# =====================================================
# 3. 检查并安装依赖
# =====================================================
echo -e "${YELLOW}📦 检查项目依赖...${NC}"

# 前端依赖
cd "$PROJECT_ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚙️  安装前端依赖...${NC}"
    npm install
    echo -e "${GREEN}✅ 前端依赖安装完成${NC}"
else
    echo -e "${GREEN}✅ 前端依赖已安装${NC}"
fi

# 后端依赖
cd "$PROJECT_ROOT/aletheia-backend"
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚙️  创建Python虚拟环境...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo -e "${GREEN}✅ 后端依赖安装完成${NC}"
else
    echo -e "${GREEN}✅ 后端虚拟环境已存在${NC}"
fi

echo ""

# =====================================================
# 4. 启动后端
# =====================================================
echo -e "${YELLOW}🚀 启动后端服务...${NC}"

cd "$PROJECT_ROOT/aletheia-backend"

# 激活虚拟环境
source venv/bin/activate

# 启动后端（后台运行，使用 setsid 防止当前 shell 退出时被级联终止）
setsid python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 > "$BACKEND_LOG_FILE" 2>&1 < /dev/null &
BACKEND_LAUNCH_PID=$!

# =====================================================
# 5. 等待后端就绪
# =====================================================
echo -e "${YELLOW}⏳ 等待后端服务就绪...${NC}"

MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 后端服务就绪！${NC}"
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${CYAN}   尝试 $RETRY_COUNT/$MAX_RETRIES...${NC}"
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}❌ 错误: 后端服务启动超时${NC}"
    echo -e "${YELLOW}💡 请查看日志: $BACKEND_LOG_FILE${NC}"
    
    # 清理
    if [ -f "$BACKEND_PID_FILE" ]; then
        kill $(cat "$BACKEND_PID_FILE") 2>/dev/null || true
        rm "$BACKEND_PID_FILE"
    fi
    exit 1
fi

# 解析实际监听 PID（uvicorn --reload 会派生子进程）
BACKEND_PID=$(lsof -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null | head -n 1)
if [ -z "$BACKEND_PID" ]; then
    BACKEND_PID=$BACKEND_LAUNCH_PID
fi
echo $BACKEND_PID > "$BACKEND_PID_FILE"

echo -e "${GREEN}✅ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
echo -e "${CYAN}   日志文件: $BACKEND_LOG_FILE${NC}"

echo ""

# =====================================================
# 6. 启动前端
# =====================================================
echo -e "${YELLOW}🚀 启动前端服务...${NC}"

cd "$PROJECT_ROOT/frontend"

# 启动前端（后台运行，避免无TTY退出）
setsid npm run dev -- --host 0.0.0.0 > "$FRONTEND_LOG_FILE" 2>&1 < /dev/null &
FRONTEND_LAUNCH_PID=$!

# 等待前端就绪并解析实际监听PID
echo -e "${YELLOW}⏳ 等待前端服务就绪...${NC}"
FRONTEND_RETRIES=0
FRONTEND_MAX_RETRIES=30

while [ $FRONTEND_RETRIES -lt $FRONTEND_MAX_RETRIES ]; do
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        break
    fi

    FRONTEND_RETRIES=$((FRONTEND_RETRIES + 1))
    sleep 1
done

if [ $FRONTEND_RETRIES -eq $FRONTEND_MAX_RETRIES ]; then
    echo -e "${RED}❌ 错误: 前端服务启动超时${NC}"
    echo -e "${YELLOW}💡 请查看日志: $FRONTEND_LOG_FILE${NC}"
    if [ -n "$FRONTEND_LAUNCH_PID" ]; then
        kill "$FRONTEND_LAUNCH_PID" 2>/dev/null || true
    fi
    exit 1
fi

FRONTEND_PID=$(lsof -t -iTCP:5173 -sTCP:LISTEN 2>/dev/null | head -n 1)
if [ -z "$FRONTEND_PID" ]; then
    FRONTEND_PID=$FRONTEND_LAUNCH_PID
fi
echo $FRONTEND_PID > "$FRONTEND_PID_FILE"

echo -e "${GREEN}✅ 前端服务已启动 (PID: $FRONTEND_PID)${NC}"
echo -e "${CYAN}   日志文件: $FRONTEND_LOG_FILE${NC}"

echo ""

# =====================================================
# 7. 显示访问信息
# =====================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}🎉 服务启动成功！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}📍 访问地址:${NC}"
echo -e "   前端: ${CYAN}http://localhost:5173${NC}"
echo -e "   后端: ${CYAN}http://localhost:8000${NC}"
echo -e "   API文档: ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}📋 进程信息:${NC}"
echo -e "   后端 PID: $BACKEND_PID"
echo -e "   前端 PID: $FRONTEND_PID"
echo ""
echo -e "${YELLOW}📝 日志文件:${NC}"
echo -e "   后端: $BACKEND_LOG_FILE"
echo -e "   前端: $FRONTEND_LOG_FILE"
echo ""
echo -e "${YELLOW}🛑 停止服务:${NC}"
echo -e "   运行: ${GREEN}./scripts/stop-dev.sh${NC}"
echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo -e "   - 使用 ${CYAN}tail -f $BACKEND_LOG_FILE${NC} 查看后端日志"
echo -e "   - 使用 ${CYAN}tail -f $FRONTEND_LOG_FILE${NC} 查看前端日志"
echo ""

exit 0
