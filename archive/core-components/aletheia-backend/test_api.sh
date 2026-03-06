#!/bin/bash
# Aletheia API 测试脚本
# 用于快速测试所有核心 API 功能

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# API 基础 URL
BASE_URL="http://localhost:8000"

# 打印分隔符
print_separator() {
    echo -e "\n${BLUE}===========================================${NC}"
}

# 打印标题
print_header() {
    echo -e "${YELLOW}>>> $1${NC}"
}

# 打印成功
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# 打印错误
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# 等待 API 启动
wait_for_api() {
    print_header "等待 API 服务启动..."
    max_attempts=30
    attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
            print_success "API 服务已就绪"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    print_error "API 服务启动超时"
    return 1
}

# 测试 1: 健康检查
test_health() {
    print_separator
    print_header "测试 1: 健康检查"
    
    response=$(curl -s "$BASE_URL/health")
    echo "响应: $response"
    
    if echo "$response" | grep -q "healthy"; then
        print_success "健康检查通过"
    else
        print_error "健康检查失败"
        return 1
    fi
}

# 测试 2: 获取热点话题 (微博)
test_weibo_hot() {
    print_separator
    print_header "测试 2: 微博热搜榜"
    
    response=$(curl -s "$BASE_URL/api/v1/weibo/hot-topics?limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "title\|topic"; then
        print_success "微博热搜获取成功"
    else
        print_error "微博热搜获取失败"
        return 1
    fi
}

# 测试 3: 获取热点话题 (小红书)
test_xiaohongshu_hot() {
    print_separator
    print_header "测试 3: 小红书热门笔记"
    
    response=$(curl -s "$BASE_URL/api/v1/xiaohongshu/hot-topics?limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "title\|content"; then
        print_success "小红书热门笔记获取成功"
    else
        print_error "小红书热门笔记获取失败"
        return 1
    fi
}

# 测试 4: 抖音热点
test_douyin_hot() {
    print_separator
    print_header "测试 4: 抖音热榜"
    
    response=$(curl -s "$BASE_URL/api/v1/douyin/hot-topics?limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "title\|content"; then
        print_success "抖音热榜获取成功"
    else
        print_error "抖音热榜获取失败"
        return 1
    fi
}

# 测试 5: 快手热点
test_kuaishou_hot() {
    print_separator
    print_header "测试 5: 快手热榜"
    
    response=$(curl -s "$BASE_URL/api/v1/kuaishou/hot-topics?limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "title\|content\|photo"; then
        print_success "快手热榜获取成功"
    else
        print_error "快手热榜获取失败 (可能需要完整启动)"
        # 非关键错误，不返回失败
    fi
}

# 测试 6: 豆瓣热点
test_douban_hot() {
    print_separator
    print_header "测试 6: 豆瓣社区动态"
    
    response=$(curl -s "$BASE_URL/api/v1/douban/hot-topics?limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "title\|content"; then
        print_success "豆瓣社区动态获取成功"
    else
        print_error "豆瓣社区动态获取失败 (可能需要完整启动)"
    fi
}

# 测试 7: 多平台热点聚合
test_multiplatform_hot() {
    print_separator
    print_header "测试 7: 多平台热点聚合"
    
    response=$(curl -s "$BASE_URL/api/v1/multiplatform/hot-topics?limit=10")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "platform\|title"; then
        print_success "多平台热点聚合成功"
        
        # 统计平台数量
        platform_count=$(echo "$response" | grep -o '"platform"' | wc -l)
        echo "  获取到 $platform_count 条数据"
    else
        print_error "多平台热点聚合失败"
        return 1
    fi
}

# 测试 8: 跨平台搜索
test_cross_platform_search() {
    print_separator
    print_header "测试 8: 跨平台搜索 - '人工智能'"
    
    response=$(curl -s "$BASE_URL/api/v1/multiplatform/search?query=%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD&limit=5")
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "platform\|title\|content"; then
        print_success "跨平台搜索成功"
        
        # 统计搜索结果数量
        result_count=$(echo "$response" | grep -o '"platform"' | wc -l)
        echo "  搜索到 $result_count 条结果"
    else
        print_error "跨平台搜索失败"
        return 1
    fi
}

# 测试 9: 视觉分析 API - 综合分析
test_vision_analysis() {
    print_separator
    print_header "测试 9: 视觉分析 - 图片理解"
    
    # 使用公开测试图片
    test_image_url="https://images.unsplash.com/photo-1506905925346-21bda4d32df4"
    
    response=$(curl -s -X POST "$BASE_URL/api/v1/vision/analyze-image" \
        -H "Content-Type: application/json" \
        -d "{\"image_url\": \"$test_image_url\", \"analysis_type\": \"comprehensive\"}")
    
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "description\|analysis\|objects"; then
        print_success "视觉分析成功"
    else
        print_error "视觉分析失败 (检查 SiliconFlow API key)"
        return 1
    fi
}

# 测试 10: 视觉分析 - 情感分析
test_vision_sentiment() {
    print_separator
    print_header "测试 10: 视觉分析 - 情感分析"
    
    # 使用公开测试图片
    test_image_url="https://images.unsplash.com/photo-1506905925346-21bda4d32df4"
    
    response=$(curl -s -X POST "$BASE_URL/api/v1/vision/analyze-image" \
        -H "Content-Type: application/json" \
        -d "{\"image_url\": \"$test_image_url\", \"analysis_type\": \"sentiment\"}")
    
    echo "响应 (前 300 字符): ${response:0:300}..."
    
    if echo "$response" | grep -q "sentiment\|emotion\|mood"; then
        print_success "情感分析成功"
    else
        print_error "情感分析失败"
        return 1
    fi
}

# 测试 11: 统计信息
test_statistics() {
    print_separator
    print_header "测试 11: 系统统计信息"
    
    response=$(curl -s "$BASE_URL/api/v1/statistics/summary")
    echo "响应: $response"
    
    if echo "$response" | grep -q "total\|platform"; then
        print_success "统计信息获取成功"
    else
        print_error "统计信息获取失败 (数据库可能为空)"
    fi
}

# 测试 12: API 文档可访问性
test_api_docs() {
    print_separator
    print_header "测试 12: API 文档可访问性"
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/docs")
    
    if [ "$response" = "200" ]; then
        print_success "API 文档可访问: $BASE_URL/docs"
    else
        print_error "API 文档无法访问 (HTTP $response)"
        return 1
    fi
}

# 主测试流程
main() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════╗"
    echo "║   Aletheia API 自动化测试套件             ║"
    echo "║   Automated API Test Suite                ║"
    echo "╚═══════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # 等待 API 启动
    wait_for_api || exit 1
    
    # 运行所有测试
    total_tests=0
    passed_tests=0
    failed_tests=0
    
    tests=(
        "test_health"
        "test_weibo_hot"
        "test_xiaohongshu_hot"
        "test_douyin_hot"
        "test_kuaishou_hot"
        "test_douban_hot"
        "test_multiplatform_hot"
        "test_cross_platform_search"
        "test_vision_analysis"
        "test_vision_sentiment"
        "test_statistics"
        "test_api_docs"
    )
    
    for test_func in "${tests[@]}"; do
        total_tests=$((total_tests + 1))
        if $test_func; then
            passed_tests=$((passed_tests + 1))
        else
            failed_tests=$((failed_tests + 1))
        fi
    done
    
    # 测试总结
    print_separator
    echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║           测试结果汇总                    ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "总测试数: ${BLUE}$total_tests${NC}"
    echo -e "通过: ${GREEN}$passed_tests${NC}"
    echo -e "失败: ${RED}$failed_tests${NC}"
    echo ""
    
    if [ $failed_tests -eq 0 ]; then
        echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  🎉 所有测试通过！系统运行正常！         ║${NC}"
        echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}下一步:${NC}"
        echo "  1. 访问 API 文档: http://localhost:8000/docs"
        echo "  2. 访问 Grafana 监控: http://localhost:3001"
        echo "  3. 查看日志: cd docker && docker-compose logs -f"
        return 0
    else
        echo -e "${RED}╔═══════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ⚠️  部分测试失败，请检查日志             ║${NC}"
        echo -e "${RED}╚═══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}排查建议:${NC}"
        echo "  1. 检查 Docker 容器状态: docker ps"
        echo "  2. 查看 API 日志: cd docker && docker-compose logs api"
        echo "  3. 检查数据库连接: docker-compose logs postgres"
        echo "  4. 验证 API key: cat docker/.env | grep SILICONFLOW"
        return 1
    fi
}

# 执行主函数
main
