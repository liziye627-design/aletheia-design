#!/bin/bash

# =====================================================
# Aletheia 开发环境停止脚本
# 用途: 优雅停止前后端服务
# =====================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# PID文件（优先新路径，兼容旧路径）
BACKEND_PID_FILE_NEW="$PROJECT_ROOT/runtime/pids/backend.pid"
FRONTEND_PID_FILE_NEW="$PROJECT_ROOT/runtime/pids/frontend.pid"
BACKEND_PID_FILE_LEGACY="$PROJECT_ROOT/.backend.pid"
FRONTEND_PID_FILE_LEGACY="$PROJECT_ROOT/.frontend.pid"

BACKEND_PID_FILE="$BACKEND_PID_FILE_NEW"
FRONTEND_PID_FILE="$FRONTEND_PID_FILE_NEW"
if [ ! -f "$BACKEND_PID_FILE" ] && [ -f "$BACKEND_PID_FILE_LEGACY" ]; then
    BACKEND_PID_FILE="$BACKEND_PID_FILE_LEGACY"
fi
if [ ! -f "$FRONTEND_PID_FILE" ] && [ -f "$FRONTEND_PID_FILE_LEGACY" ]; then
    FRONTEND_PID_FILE="$FRONTEND_PID_FILE_LEGACY"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Aletheia 开发环境停止${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

STOPPED_COUNT=0

# =====================================================
# 停止后端
# =====================================================
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e "${YELLOW}🛑 停止后端服务 (PID: $BACKEND_PID)...${NC}"
        kill "$BACKEND_PID" 2>/dev/null || true
        
        # 等待进程结束
        for i in {1..10}; do
            if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        
        # 如果还没结束，强制杀死
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo -e "${YELLOW}   强制停止后端服务...${NC}"
            kill -9 "$BACKEND_PID" 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✅ 后端服务已停止${NC}"
        STOPPED_COUNT=$((STOPPED_COUNT + 1))
    else
        echo -e "${YELLOW}⚠️  后端服务未运行 (PID: $BACKEND_PID)${NC}"
    fi
    
    rm "$BACKEND_PID_FILE"
else
    echo -e "${YELLOW}ℹ️  未找到后端PID文件${NC}"
fi

# =====================================================
# 停止前端
# =====================================================
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo -e "${YELLOW}🛑 停止前端服务 (PID: $FRONTEND_PID)...${NC}"
        kill "$FRONTEND_PID" 2>/dev/null || true
        
        # 等待进程结束
        for i in {1..10}; do
            if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        
        # 如果还没结束，强制杀死
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo -e "${YELLOW}   强制停止前端服务...${NC}"
            kill -9 "$FRONTEND_PID" 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✅ 前端服务已停止${NC}"
        STOPPED_COUNT=$((STOPPED_COUNT + 1))
    else
        echo -e "${YELLOW}⚠️  前端服务未运行 (PID: $FRONTEND_PID)${NC}"
    fi
    
    rm "$FRONTEND_PID_FILE"
else
    echo -e "${YELLOW}ℹ️  未找到前端PID文件${NC}"
fi

# =====================================================
# 清理临时文件
# =====================================================
echo ""
echo -e "${YELLOW}🧹 清理临时文件...${NC}"

# 兼容清理旧PID文件
if [ -f "$BACKEND_PID_FILE_LEGACY" ]; then
    rm -f "$BACKEND_PID_FILE_LEGACY"
fi
if [ -f "$FRONTEND_PID_FILE_LEGACY" ]; then
    rm -f "$FRONTEND_PID_FILE_LEGACY"
fi

echo -e "${GREEN}✅ 清理完成${NC}"

# =====================================================
# 总结
# =====================================================
echo ""
echo -e "${BLUE}========================================${NC}"
if [ $STOPPED_COUNT -gt 0 ]; then
    echo -e "${GREEN}✅ 已停止 $STOPPED_COUNT 个服务${NC}"
else
    echo -e "${YELLOW}ℹ️  没有运行中的服务${NC}"
fi
echo -e "${BLUE}========================================${NC}"
echo ""

exit 0
