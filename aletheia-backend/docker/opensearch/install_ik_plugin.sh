#!/bin/bash
# Install IK Analysis Plugin for OpenSearch
# 为 OpenSearch 安装 IK 中文分词插件
#
# Usage:
#   ./install_ik_plugin.sh [opensearch_version]
#
# Default version: 2.11.0

set -e

OPENSEARCH_VERSION=${1:-2.11.0}
IK_VERSION="${OPENSEARCH_VERSION}"

# IK Plugin download URL
IK_PLUGIN_URL="https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v${IK_VERSION}/elasticsearch-analysis-ik-${IK_VERSION}.zip"

echo "=========================================="
echo "Installing IK Analysis Plugin for OpenSearch ${OPENSEARCH_VERSION}"
echo "=========================================="

# Create plugin directory
PLUGIN_DIR="./opensearch/ik"
mkdir -p ${PLUGIN_DIR}

# Download IK plugin
echo "Downloading IK plugin..."
if command -v wget &> /dev/null; then
    wget -O /tmp/ik-plugin.zip ${IK_PLUGIN_URL}
elif command -v curl &> /dev/null; then
    curl -L -o /tmp/ik-plugin.zip ${IK_PLUGIN_URL}
else
    echo "Error: wget or curl required"
    exit 1
fi

# Extract plugin
echo "Extracting plugin..."
unzip -o /tmp/ik-plugin.zip -d ${PLUGIN_DIR}

# Create custom dictionary directory
mkdir -p ${PLUGIN_DIR}/config/custom

# Create custom dictionary files
echo "Creating custom dictionaries..."

# Custom main dictionary (extend IK's default)
cat > ${PLUGIN_DIR}/config/custom/ext_dict.dic << 'EOF'
人工智能
机器学习
深度学习
神经网络
自然语言处理
计算机视觉
大数据
云计算
区块链
元宇宙
虚拟现实
增强现实
量子计算
物联网
5G
6G
新能源
碳中和
碳达峰
数字经济
数字货币
芯片
半导体
集成电路
EOF

# Custom stop words
cat > ${PLUGIN_DIR}/config/custom/ext_stopwords.dic << 'EOF'
了
的
是
在
有
和
与
或
但
而
如果
因为
所以
虽然
但是
然而
EOF

# Update IK configuration
cat > ${PLUGIN_DIR}/config/IKAnalyzer.cfg.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <comment>IK Analyzer 扩展配置</comment>
    <!-- 用户可以在这里配置自己的扩展字典 -->
    <entry key="ext_dict">custom/ext_dict.dic</entry>
    <!-- 用户可以在这里配置自己的扩展停止词字典 -->
    <entry key="ext_stopwords">custom/ext_stopwords.dic</entry>
    <!-- 用户可以在这里配置远程扩展字典 -->
    <!-- <entry key="remote_ext_dict">http://localhost:8080/dict</entry> -->
    <!-- 用户可以在这里配置远程扩展停止词字典 -->
    <!-- <entry key="remote_ext_stopwords">http://localhost:8080/stopwords</entry> -->
</properties>
EOF

# Clean up
rm /tmp/ik-plugin.zip

echo "=========================================="
echo "IK Plugin installed successfully!"
echo "Plugin directory: ${PLUGIN_DIR}"
echo ""
echo "Custom dictionaries created:"
echo "  - ext_dict.dic: Custom word dictionary"
echo "  - ext_stopwords.dic: Custom stop words"
echo ""
echo "Next steps:"
echo "  1. Start OpenSearch: docker-compose up -d"
echo "  2. Create indexes: python scripts/create_opensearch_indexes.py"
echo "=========================================="