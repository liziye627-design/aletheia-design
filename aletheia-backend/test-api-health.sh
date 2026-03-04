#!/bin/bash

# ========================================
# Aletheia API 全面健康检测脚本
# ========================================

BASE_URL="http://localhost:8000"
API_BASE="${BASE_URL}/api/v1"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 统计变量
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 测试结果数组
declare -a FAILED_ENDPOINTS

# 测试函数
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    echo -e "\n${BLUE}[测试 $TOTAL_TESTS]${NC} $description"
    echo -e "${YELLOW}$method${NC} $endpoint"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$endpoint")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    # 判断是否成功
    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
        echo -e "${GREEN}✓ 成功${NC} (HTTP $http_code)"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        # 显示响应摘要
        if [ ! -z "$body" ]; then
            echo "$body" | python3 -m json.tool 2>/dev/null | head -10 || echo "$body" | head -5
        fi
    else
        echo -e "${RED}✗ 失败${NC} (HTTP $http_code)"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_ENDPOINTS+=("$method $endpoint - HTTP $http_code")
        # 显示错误信息
        if [ ! -z "$body" ]; then
            echo -e "${RED}错误详情:${NC}"
            echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        fi
    fi
}

echo "=========================================="
echo "  Aletheia API 全面健康检测"
echo "=========================================="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ==========================================
# 1. 基础健康检查
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}1. 基础健康检查${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

test_endpoint "GET" "${BASE_URL}/" "" "根端点"
test_endpoint "GET" "${BASE_URL}/health" "" "健康检查端点"

# ==========================================
# 2. 认证模块 (Auth)
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}2. 认证模块 (Auth)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 注册测试用户
RANDOM_USER="test_$(date +%s)"
test_endpoint "POST" "${API_BASE}/auth/register" \
    "{\"username\":\"$RANDOM_USER\",\"email\":\"${RANDOM_USER}@test.com\",\"password\":\"Test123456\"}" \
    "用户注册"

# 登录
test_endpoint "POST" "${API_BASE}/auth/login" \
    "{\"username\":\"$RANDOM_USER\",\"password\":\"Test123456\"}" \
    "用户登录"

# ==========================================
# 3. 情报分析模块 (Intelligence)
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}3. 情报分析模块 (Intelligence)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# POST - 分析情报
echo -e "\n${YELLOW}3.1 POST 端点测试${NC}"
test_endpoint "POST" "${API_BASE}/intel/analyze" \
    "{\"content\":\"这是一条测试新闻内容\",\"source\":\"test\",\"platform\":\"manual\"}" \
    "分析单条情报"

# 保存intel_id用于后续测试
INTEL_RESPONSE=$(curl -s -X POST "${API_BASE}/intel/analyze" \
    -H "Content-Type: application/json" \
    -d '{"content":"测试情报用于GET和DELETE","source":"test","platform":"manual"}')
INTEL_ID=$(echo "$INTEL_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intel_id', ''))" 2>/dev/null)

test_endpoint "POST" "${API_BASE}/intel/batch" \
    "{\"items\":[{\"content\":\"批量测试1\",\"source\":\"test\"},{\"content\":\"批量测试2\",\"source\":\"test\"}]}" \
    "批量分析情报"

test_endpoint "POST" "${API_BASE}/intel/search" \
    "{\"query\":\"测试\",\"limit\":10}" \
    "搜索情报"

# GET - 查询情报
echo -e "\n${YELLOW}3.2 GET 端点测试${NC}"
test_endpoint "GET" "${API_BASE}/intel/trending" "" "获取热门话题"

if [ ! -z "$INTEL_ID" ]; then
    test_endpoint "GET" "${API_BASE}/intel/${INTEL_ID}" "" "根据ID获取情报详情"
fi

# DELETE - 删除情报
echo -e "\n${YELLOW}3.3 DELETE 端点测试${NC}"
if [ ! -z "$INTEL_ID" ]; then
    test_endpoint "DELETE" "${API_BASE}/intel/${INTEL_ID}" "" "删除情报"
    
    # 验证删除
    echo -e "\n${YELLOW}验证删除结果:${NC}"
    test_endpoint "GET" "${API_BASE}/intel/${INTEL_ID}" "" "验证情报已删除(应该404)"
fi

# ==========================================
# 4. 增强情报分析模块
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}4. 增强情报分析模块${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# POST - 增强分析
test_endpoint "POST" "${API_BASE}/intel/enhanced/analyze" \
    "{\"content\":\"增强分析测试内容\",\"source\":\"test\",\"platform\":\"manual\"}" \
    "标准增强分析"

test_endpoint "POST" "${API_BASE}/intel/enhanced/analyze/enhanced" \
    "{\"content\":\"深度增强分析测试\",\"source\":\"test\",\"platform\":\"manual\"}" \
    "深度增强分析"

# 创建一个用于测试的增强情报
ENHANCED_RESPONSE=$(curl -s -X POST "${API_BASE}/intel/enhanced/analyze" \
    -H "Content-Type: application/json" \
    -d '{"content":"用于测试推理链的情报","source":"test","platform":"manual"}')
ENHANCED_ID=$(echo "$ENHANCED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intel_id', ''))" 2>/dev/null)

# GET - 查询增强分析结果
if [ ! -z "$ENHANCED_ID" ]; then
    test_endpoint "GET" "${API_BASE}/intel/enhanced/${ENHANCED_ID}" "" "获取增强分析详情"
    test_endpoint "GET" "${API_BASE}/intel/enhanced/${ENHANCED_ID}/reasoning-chain" "" "获取推理链"
    test_endpoint "GET" "${API_BASE}/intel/enhanced/${ENHANCED_ID}/reasoning-visualization" "" "获取推理可视化"
fi

test_endpoint "GET" "${API_BASE}/intel/enhanced/trending" "" "获取增强版热门话题"

# POST - 搜索和批量
test_endpoint "POST" "${API_BASE}/intel/enhanced/search" \
    "{\"query\":\"测试\",\"limit\":5}" \
    "增强搜索"

test_endpoint "POST" "${API_BASE}/intel/enhanced/batch" \
    "{\"items\":[{\"content\":\"增强批量1\",\"source\":\"test\"}]}" \
    "增强批量分析"

# DELETE - 删除增强情报
if [ ! -z "$ENHANCED_ID" ]; then
    test_endpoint "DELETE" "${API_BASE}/intel/enhanced/${ENHANCED_ID}" "" "删除增强情报"
fi

# ==========================================
# 5. 多平台数据模块
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}5. 多平台数据模块${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# GET - 平台列表
test_endpoint "GET" "${API_BASE}/multiplatform/platforms" "" "获取支持的平台列表"

# POST - 搜索和分析
test_endpoint "POST" "${API_BASE}/multiplatform/search" \
    "{\"query\":\"测试\",\"platforms\":[\"weibo\"],\"limit\":5}" \
    "多平台搜索"

test_endpoint "POST" "${API_BASE}/multiplatform/analyze-credibility" \
    "{\"content\":\"可信度分析测试\",\"platforms\":[\"weibo\"]}" \
    "可信度分析"

test_endpoint "POST" "${API_BASE}/multiplatform/hot-topics" \
    "{\"platforms\":[\"weibo\"],\"limit\":10}" \
    "热门话题"

# GET - Playwright健康检查
test_endpoint "GET" "${API_BASE}/multiplatform/playwright/health" "" "Playwright健康检查"

# ==========================================
# 6. 视觉分析模块
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}6. 视觉分析模块${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# GET - 健康检查
test_endpoint "GET" "${API_BASE}/vision/vision/health" "" "视觉分析健康检查"

# POST - 图像分析 (使用测试URL)
test_endpoint "POST" "${API_BASE}/vision/vision/analyze-image" \
    "{\"image_url\":\"https://via.placeholder.com/150\"}" \
    "图像分析"

test_endpoint "POST" "${API_BASE}/vision/vision/detect-fake-image" \
    "{\"image_url\":\"https://via.placeholder.com/150\"}" \
    "假图检测"

# ==========================================
# 7. 报告模块
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}7. 报告模块${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# POST - 生成报告
test_endpoint "POST" "${API_BASE}/reports/generate" \
    "{\"title\":\"测试报告\",\"content\":\"报告内容\",\"report_type\":\"analysis\"}" \
    "生成报告"

# GET - 报告列表
test_endpoint "GET" "${API_BASE}/reports/" "" "获取报告列表"

# ==========================================
# 8. Feeds模块
# ==========================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}8. Feeds模块${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# GET - Feeds列表
test_endpoint "GET" "${API_BASE}/feeds/" "" "获取Feeds列表"

# POST - Feeds过滤
test_endpoint "POST" "${API_BASE}/feeds/filter" \
    "{\"platform\":\"weibo\",\"limit\":10}" \
    "Feeds过滤"

# ==========================================
# 测试总结
# ==========================================
echo -e "\n${BLUE}=========================================="
echo "  测试总结"
echo "==========================================${NC}"
echo ""
echo -e "总测试数: ${BLUE}$TOTAL_TESTS${NC}"
echo -e "通过: ${GREEN}$PASSED_TESTS${NC}"
echo -e "失败: ${RED}$FAILED_TESTS${NC}"
echo -e "成功率: $(awk "BEGIN {printf \"%.1f%%\", ($PASSED_TESTS/$TOTAL_TESTS)*100}")"
echo ""

if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}失败的端点列表:${NC}"
    for endpoint in "${FAILED_ENDPOINTS[@]}"; do
        echo -e "  ${RED}✗${NC} $endpoint"
    done
    echo ""
fi

echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 返回状态码
if [ $FAILED_TESTS -eq 0 ]; then
    exit 0
else
    exit 1
fi
