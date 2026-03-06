#!/bin/bash

# 核心API测试 - POST/GET/DELETE

BASE_URL="http://localhost:8000/api/v1"

echo "=========================================="
echo "  核心API功能测试 (POST/GET/DELETE)"
echo "=========================================="

# 测试计数
PASS=0
FAIL=0

test_api() {
    local name=$1
    local method=$2
    local url=$3
    local data=$4
    
    echo -e "\n【测试】$name"
    echo "  $method $url"
    
    if [ "$method" = "POST" ]; then
        result=$(curl -s -w "\n%{http_code}" -X POST "$url" -H "Content-Type: application/json" -d "$data")
    elif [ "$method" = "GET" ]; then
        result=$(curl -s -w "\n%{http_code}" "$url")
    elif [ "$method" = "DELETE" ]; then
        result=$(curl -s -w "\n%{http_code}" -X DELETE "$url")
    fi
    
    code=$(echo "$result" | tail -n1)
    body=$(echo "$result" | sed '$d')
    
    if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
        echo "  ✓ 成功 (HTTP $code)"
        PASS=$((PASS+1))
        echo "$body" | python3 -m json.tool 2>/dev/null | head -5 || echo "$body" | head -3
    else
        echo "  ✗ 失败 (HTTP $code)"
        FAIL=$((FAIL+1))
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    fi
    
    echo "$body"  # 返回body供后续使用
}

# ==========================================
# 情报分析 - 完整流程测试
# ==========================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "情报分析模块 - 完整CRUD流程"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. POST - 创建情报
echo -e "\n1️⃣  POST - 创建情报"
response=$(test_api "创建情报" "POST" "${BASE_URL}/intel/analyze" \
    '{"content":"这是一条测试情报,用于测试完整的CRUD流程","source":"test_source","platform":"manual"}')

# 提取intel_id
intel_id=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('intel_id', ''))" 2>/dev/null)

if [ -z "$intel_id" ]; then
    echo "  ⚠️  无法获取intel_id,跳过后续测试"
else
    echo "  📝 Intel ID: $intel_id"
    
    # 2. GET - 查询情报
    echo -e "\n2️⃣  GET - 查询情报详情"
    test_api "查询情报" "GET" "${BASE_URL}/intel/${intel_id}" > /dev/null
    
    # 3. DELETE - 删除情报
    echo -e "\n3️⃣  DELETE - 删除情报"
    test_api "删除情报" "DELETE" "${BASE_URL}/intel/${intel_id}" > /dev/null
    
    # 4. GET - 验证删除
    echo -e "\n4️⃣  GET - 验证删除(应该返回404)"
    test_api "验证删除" "GET" "${BASE_URL}/intel/${intel_id}" > /dev/null
fi

# ==========================================
# 增强情报分析 - 完整流程测试
# ==========================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "增强情报分析模块 - 完整CRUD流程"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. POST - 创建增强情报
echo -e "\n1️⃣  POST - 创建增强情报"
response=$(test_api "创建增强情报" "POST" "${BASE_URL}/intel/enhanced/analyze" \
    '{"content":"增强分析测试情报","source":"test","platform":"manual"}')

enhanced_id=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('intel_id', ''))" 2>/dev/null)

if [ ! -z "$enhanced_id" ]; then
    echo "  📝 Enhanced Intel ID: $enhanced_id"
    
    # 2. GET - 查询增强情报
    echo -e "\n2️⃣  GET - 查询增强情报详情"
    test_api "查询增强情报" "GET" "${BASE_URL}/intel/enhanced/${enhanced_id}" > /dev/null
    
    # 3. GET - 获取推理链
    echo -e "\n3️⃣  GET - 获取推理链"
    test_api "获取推理链" "GET" "${BASE_URL}/intel/enhanced/${enhanced_id}/reasoning-chain" > /dev/null
    
    # 4. DELETE - 删除增强情报
    echo -e "\n4️⃣  DELETE - 删除增强情报"
    test_api "删除增强情报" "DELETE" "${BASE_URL}/intel/enhanced/${enhanced_id}" > /dev/null
fi

# ==========================================
# 批量操作测试
# ==========================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "批量操作测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n📦 POST - 批量分析"
test_api "批量分析" "POST" "${BASE_URL}/intel/batch" \
    '{"items":[{"content":"批量测试1","source":"test"},{"content":"批量测试2","source":"test"}]}' > /dev/null

echo -e "\n📦 POST - 增强批量分析"
test_api "增强批量分析" "POST" "${BASE_URL}/intel/enhanced/batch" \
    '{"items":[{"content":"增强批量1","source":"test"}]}' > /dev/null

# ==========================================
# 搜索功能测试
# ==========================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "搜索功能测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n🔍 POST - 搜索情报"
test_api "搜索情报" "POST" "${BASE_URL}/intel/search" \
    '{"query":"测试","limit":5}' > /dev/null

echo -e "\n🔍 POST - 增强搜索"
test_api "增强搜索" "POST" "${BASE_URL}/intel/enhanced/search" \
    '{"query":"测试","limit":5}' > /dev/null

# ==========================================
# 热门话题测试
# ==========================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "热门话题测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n🔥 GET - 热门话题"
test_api "热门话题" "GET" "${BASE_URL}/intel/trending" > /dev/null

echo -e "\n🔥 GET - 增强热门话题"
test_api "增强热门话题" "GET" "${BASE_URL}/intel/enhanced/trending" > /dev/null

# ==========================================
# 测试总结
# ==========================================
echo -e "\n=========================================="
echo "  测试总结"
echo "=========================================="
echo "通过: $PASS"
echo "失败: $FAIL"
echo "总计: $((PASS+FAIL))"
echo "成功率: $(awk "BEGIN {if($PASS+$FAIL>0) printf \"%.1f%%\", ($PASS/($PASS+$FAIL))*100; else print \"N/A\"}")"
echo "=========================================="

if [ $FAIL -eq 0 ]; then
    echo "✅ 所有测试通过!"
    exit 0
else
    echo "⚠️  有 $FAIL 个测试失败"
    exit 1
fi
