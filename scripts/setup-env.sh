#!/bin/bash

# =====================================================
# Aletheia 环境配置脚本
# 用途: 创建和验证前后端环境变量配置
# =====================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Aletheia 环境配置脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =====================================================
# 1. 配置前端环境变量
# =====================================================
echo -e "${YELLOW}📝 配置前端环境变量...${NC}"

FRONTEND_DIR="$PROJECT_ROOT/frontend"
FRONTEND_ENV="$FRONTEND_DIR/.env"
FRONTEND_ENV_EXAMPLE="$FRONTEND_DIR/.env.example"

if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}❌ 错误: 前端目录不存在: $FRONTEND_DIR${NC}"
    exit 1
fi

cd "$FRONTEND_DIR"

if [ -f "$FRONTEND_ENV" ]; then
    echo -e "${GREEN}✅ 前端 .env 文件已存在${NC}"
else
    if [ -f "$FRONTEND_ENV_EXAMPLE" ]; then
        echo -e "${YELLOW}⚙️  从 .env.example 创建 .env 文件...${NC}"
        cp "$FRONTEND_ENV_EXAMPLE" "$FRONTEND_ENV"
        echo -e "${GREEN}✅ 前端 .env 文件创建成功${NC}"
    else
        echo -e "${YELLOW}⚠️  .env.example 不存在，创建默认配置...${NC}"
        cat > "$FRONTEND_ENV" << 'EOF'
# API 基础地址
VITE_API_BASE_URL=http://localhost:8000/api/v1

EOF
        echo -e "${GREEN}✅ 前端 .env 文件创建成功（使用默认配置）${NC}"
    fi
fi

# 验证前端必需配置项
echo -e "${YELLOW}🔍 验证前端配置...${NC}"
if grep -q "VITE_API_BASE_URL" "$FRONTEND_ENV"; then
    API_BASE_URL=$(grep "VITE_API_BASE_URL" "$FRONTEND_ENV" | cut -d '=' -f2)
    echo -e "${GREEN}✅ VITE_API_BASE_URL: $API_BASE_URL${NC}"
else
    echo -e "${RED}❌ 错误: 缺少 VITE_API_BASE_URL 配置${NC}"
    echo -e "${YELLOW}💡 请在 $FRONTEND_ENV 中添加:${NC}"
    echo -e "   VITE_API_BASE_URL=http://localhost:8000/api/v1"
    exit 1
fi

# =====================================================
# 2. 配置后端环境变量
# =====================================================
echo ""
echo -e "${YELLOW}📝 配置后端环境变量...${NC}"

BACKEND_DIR="$PROJECT_ROOT/aletheia-backend"
BACKEND_ENV="$BACKEND_DIR/.env"
BACKEND_ENV_EXAMPLE="$BACKEND_DIR/.env.example"

if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}❌ 错误: 后端目录不存在: $BACKEND_DIR${NC}"
    exit 1
fi

cd "$BACKEND_DIR"

if [ -f "$BACKEND_ENV" ]; then
    echo -e "${GREEN}✅ 后端 .env 文件已存在${NC}"
else
    if [ -f "$BACKEND_ENV_EXAMPLE" ]; then
        echo -e "${YELLOW}⚙️  从 .env.example 创建 .env 文件...${NC}"
        cp "$BACKEND_ENV_EXAMPLE" "$BACKEND_ENV"
        echo -e "${GREEN}✅ 后端 .env 文件创建成功${NC}"
    else
        echo -e "${RED}❌ 错误: 后端 .env.example 文件不存在${NC}"
        exit 1
    fi
fi

# 验证后端必需配置项
echo -e "${YELLOW}🔍 验证后端配置...${NC}"

# 检查 CORS 配置
if grep -q "BACKEND_CORS_ORIGINS" "$BACKEND_ENV"; then
    echo -e "${GREEN}✅ BACKEND_CORS_ORIGINS 已配置${NC}"
else
    echo -e "${YELLOW}⚠️  未找到 BACKEND_CORS_ORIGINS，使用默认值${NC}"
fi

# 检查 LLM API Key（至少需要一个）
HAS_LLM_KEY=false

if grep -q "^SILICONFLOW_API_KEY=" "$BACKEND_ENV" && ! grep -q "^SILICONFLOW_API_KEY=$" "$BACKEND_ENV"; then
    echo -e "${GREEN}✅ SILICONFLOW_API_KEY 已配置${NC}"
    HAS_LLM_KEY=true
fi

if grep -q "^OPENAI_API_KEY=" "$BACKEND_ENV" && ! grep -q "^OPENAI_API_KEY=$" "$BACKEND_ENV"; then
    echo -e "${GREEN}✅ OPENAI_API_KEY 已配置${NC}"
    HAS_LLM_KEY=true
fi

if grep -q "^KIMI_API_KEY=" "$BACKEND_ENV" && ! grep -q "^KIMI_API_KEY=$" "$BACKEND_ENV"; then
    echo -e "${GREEN}✅ KIMI_API_KEY 已配置${NC}"
    HAS_LLM_KEY=true
fi

if [ "$HAS_LLM_KEY" = false ]; then
    echo -e "${RED}❌ 错误: 未配置任何 LLM API Key${NC}"
    echo -e "${YELLOW}💡 请在 $BACKEND_ENV 中至少配置以下之一:${NC}"
    echo -e "   - SILICONFLOW_API_KEY=your_key_here"
    echo -e "   - OPENAI_API_KEY=your_key_here"
    echo -e "   - KIMI_API_KEY=your_key_here"
    exit 1
fi

# 检查数据库配置（可选，因为可以使用SQLite）
if grep -q "^POSTGRES_SERVER=" "$BACKEND_ENV"; then
    echo -e "${GREEN}✅ PostgreSQL 配置已设置${NC}"
else
    echo -e "${YELLOW}ℹ️  未配置 PostgreSQL，将使用 SQLite${NC}"
fi

# =====================================================
# 3. 配置总结
# =====================================================
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ 环境配置完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}📋 配置文件位置:${NC}"
echo -e "   前端: $FRONTEND_ENV"
echo -e "   后端: $BACKEND_ENV"
echo ""
echo -e "${YELLOW}🚀 下一步:${NC}"
echo -e "   1. 检查并编辑配置文件（如需要）"
echo -e "   2. 运行 ${GREEN}./scripts/start-dev.sh${NC} 启动服务"
echo ""

exit 0
