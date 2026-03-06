#!/bin/bash
# ============================================================
# OpenSearch 部署脚本
# Aletheia 证据库 - OpenSearch 部署
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
OPENSEARCH_DIR="$PROJECT_ROOT/docker/opensearch"

echo "============================================================"
echo "Aletheia OpenSearch 部署脚本"
echo "============================================================"

# 检查 Docker 是否可用
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker 未安装或未集成到 WSL"
        echo ""
        echo "请在 Docker Desktop 中启用 WSL 集成："
        echo "  1. 打开 Docker Desktop"
        echo "  2. 进入 Settings > Resources > WSL Integration"
        echo "  3. 启用你的 WSL 发行版"
        echo "  4. 点击 Apply & Restart"
        echo ""
        echo "或者使用以下替代方案："
        echo "  - 使用 Windows PowerShell 运行此脚本"
        echo "  - 手动安装 OpenSearch (非 Docker)"
        return 1
    fi

    if ! docker info &> /dev/null; then
        echo "❌ Docker 未运行"
        echo "请启动 Docker Desktop 后重试"
        return 1
    fi

    echo "✅ Docker 可用"
    return 0
}

# 安装 IK 中文分词插件
install_ik_plugin() {
    echo ""
    echo "📦 安装 IK 中文分词插件..."

    IK_DIR="$OPENSEARCH_DIR/ik"
    mkdir -p "$IK_DIR"

    # 下载 IK 插件
    IK_VERSION="2.11.0"
    IK_URL="https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v${IK_VERSION}/elasticsearch-analysis-ik-${IK_VERSION}.zip"

    if [ ! -f "$IK_DIR/elasticsearch-analysis-ik-${IK_VERSION}.zip" ]; then
        echo "  下载 IK 插件..."
        wget -q "$IK_URL" -O "$IK_DIR/elasticsearch-analysis-ik-${IK_VERSION}.zip" || {
            echo "  ⚠️  下载失败，将使用容器内安装"
        }
    fi

    # 创建自定义词典
    echo "  创建自定义词典..."
    cat > "$IK_DIR/custom.dic" << 'EOF'
人工智能
机器学习
深度学习
神经网络
自然语言处理
大语言模型
知识图谱
虚假信息
事实核查
证据链
EOF

    echo "✅ IK 插件准备完成"
}

# 启动 OpenSearch
start_opensearch() {
    echo ""
    echo "🚀 启动 OpenSearch 集群..."

    cd "$OPENSEARCH_DIR"

    # 检查是否已运行
    if docker-compose ps | grep -q "Up"; then
        echo "  OpenSearch 已在运行"
        return 0
    fi

    # 启动服务
    docker-compose up -d

    echo ""
    echo "⏳ 等待 OpenSearch 启动..."
    sleep 30

    # 检查健康状态
    for i in {1..30}; do
        if curl -s "http://localhost:9200/_cluster/health" | grep -q "green\|yellow"; then
            echo "✅ OpenSearch 启动成功"
            return 0
        fi
        echo "  等待中... ($i/30)"
        sleep 5
    done

    echo "⚠️  OpenSearch 启动超时，请检查日志"
    return 1
}

# 创建索引
create_indexes() {
    echo ""
    echo "📊 创建证据库索引..."

    cd "$PROJECT_ROOT"

    # 激活虚拟环境
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi

    # 运行索引创建脚本
    python scripts/create_opensearch_indexes.py || {
        echo "  使用 curl 创建索引..."

        # 创建 evidence 索引
        curl -X PUT "http://localhost:9200/evidence" -H 'Content-Type: application/json' -d'
        {
            "settings": {
                "index": {
                    "number_of_shards": 2,
                    "number_of_replicas": 1
                },
                "analysis": {
                    "analyzer": {
                        "ik_smart_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_smart"
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "doc_id": { "type": "keyword" },
                    "title": { "type": "text", "analyzer": "ik_smart_analyzer" },
                    "content_text": { "type": "text", "analyzer": "ik_smart_analyzer" },
                    "platform": { "type": "keyword" },
                    "source_domain": { "type": "keyword" },
                    "source_tier": { "type": "keyword" },
                    "evidence_score": { "type": "float" },
                    "publish_time": { "type": "date" },
                    "crawl_time": { "type": "date" },
                    "embedding": { "type": "knn_vector", "dimension": 1024 }
                }
            }
        }'

        # 创建 search_hits 索引
        curl -X PUT "http://localhost:9200/search_hits" -H 'Content-Type: application/json' -d'
        {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1
                }
            },
            "mappings": {
                "properties": {
                    "hit_id": { "type": "keyword" },
                    "query": { "type": "keyword" },
                    "platform": { "type": "keyword" },
                    "hit_title": { "type": "text" },
                    "hit_url": { "type": "keyword" },
                    "rank": { "type": "integer" },
                    "captured_at": { "type": "date" }
                }
            }
        }'
    }

    echo "✅ 索引创建完成"
}

# 显示状态
show_status() {
    echo ""
    echo "============================================================"
    echo "OpenSearch 部署状态"
    echo "============================================================"

    echo ""
    echo "连接信息："
    echo "  - OpenSearch API: http://localhost:9200"
    echo "  - OpenSearch Dashboards: http://localhost:5601"
    echo "  - 用户名: admin"
    echo "  - 密码: admin"
    echo ""
    echo "测试命令："
    echo "  curl http://localhost:9200/_cluster/health?pretty"
    echo "  curl http://localhost:9200/_cat/indices?v"
    echo ""
    echo "停止服务："
    echo "  cd $OPENSEARCH_DIR && docker-compose down"
    echo "============================================================"
}

# 主流程
main() {
    if ! check_docker; then
        echo ""
        echo "💡 提示: 你可以手动运行以下命令启动 OpenSearch："
        echo ""
        echo "  # Windows PowerShell:"
        echo "  cd $OPENSEARCH_DIR"
        echo "  docker-compose up -d"
        echo ""
        echo "  # 创建索引:"
        echo "  python scripts/create_opensearch_indexes.py"
        exit 1
    fi

    install_ik_plugin
    start_opensearch
    create_indexes
    show_status
}

main "$@"