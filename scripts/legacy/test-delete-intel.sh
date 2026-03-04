#!/bin/bash

# 简单的API结构测试 - 不依赖LLM

BASE_URL="http://localhost:8000/api/v1"

echo "=========================================="
echo "  API结构测试 (不依赖LLM)"
echo "=========================================="

# 测试计数
PASS=0
FAIL=0

test_endpoint() {
    local name=$1
    local method=$2
    local url=$3
    local expected_code=$4
    
    echo -e "\n【测试】$name"
    echo "  $method $url"
    echo "  期望: HTTP $expected_code"
    
    if [ "$method" = "GET" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    elif [ "$method" = "DELETE" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$url")
    fi
    
    if [ "$code" = "$expected_code" ]; then
        echo "  ✓ 成功 (HTTP $code)"
        PASS=$((PASS+1))
    else
        echo "  ✗ 失败 (HTTP $code, 期望 $expected_code)"
        FAIL=$((FAIL+1))
    fi
}

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "基础端点结构测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 健康检查
test_endpoint "健康检查" "GET" "http://localhost:8000/health" "200"

# GET端点 - 应该返回404或501 (未实现)
test_endpoint "获取不存在的情报" "GET" "${BASE_URL}/intel/test-id-123" "501"
test_endpoint "获取不存在的增强情报" "GET" "${BASE_URL}/intel/enhanced/test-id-123" "404"

# DELETE端点 - 应该返回200 (即使不存在也返回成功)
test_endpoint "删除情报" "DELETE" "${BASE_URL}/intel/test-id-123" "200"
test_endpoint "删除增强情报" "DELETE" "${BASE_URL}/intel/enhanced/test-id-123" "200"

# 热门话题
test_endpoint "热门话题" "GET" "${BASE_URL}/intel/trending" "501"
test_endpoint "增强热门话题" "GET" "${BASE_URL}/intel/enhanced/trending" "200"

echo -e "\n=========================================="
echo "  测试总结"
echo "=========================================="
echo "通过: $PASS"
echo "失败: $FAIL"
echo "总计: $((PASS+FAIL))"
echo "=========================================="

if [ $FAIL -eq 0 ]; then
    echo "✅ 所有端点结构正常!"
    exit 0
else
    echo "⚠️  有 $FAIL 个端点异常"
    exit 1
fi
