#!/bin/bash

echo "=========================================="
echo "  Aletheia 快速功能测试"
echo "=========================================="

BASE_URL="http://localhost:8000"

echo -e "\n1️⃣  健康检查"
curl -s ${BASE_URL}/health | python3 -m json.tool

echo -e "\n\n2️⃣  API 文档"
echo "访问: ${BASE_URL}/docs"

echo -e "\n\n3️⃣  测试增强版情报分析"
curl -s -X POST ${BASE_URL}/api/v1/intel/enhanced/analyze \
  -H "Content-Type: application/json" \
  -d '{"content":"这是一条测试情报","source":"test","platform":"manual"}' \
  | python3 -m json.tool | head -50

echo -e "\n\n4️⃣  查看热门话题"
curl -s ${BASE_URL}/api/v1/intel/enhanced/trending | python3 -m json.tool

echo -e "\n\n=========================================="
echo "  测试完成！"
echo "=========================================="
echo "📝 完整 API 文档: http://localhost:8000/docs"
echo "🔍 健康检查: http://localhost:8000/health"
echo "=========================================="
