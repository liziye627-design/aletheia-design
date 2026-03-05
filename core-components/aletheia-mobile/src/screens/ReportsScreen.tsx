/**
 * Verification Report Screen - 验真报告
 * 核心：分层信源真实接口调用 + 报告生成入库
 */

import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';

import { Card, Button, CoreChatHeader, CredibilityBadge } from '../components';
import { documentExportService, historyService, verificationService } from '../services';
import { theme } from '../utils/theme';

type LayerStatus = 'ready' | 'running' | 'done' | 'failed';

type SourceLayer = {
  id: string;
  level: 1 | 2 | 3 | 4;
  title: string;
  description: string;
  status: LayerStatus;
  summary?: string;
};

type EvidenceNode = {
  id: string;
  label: string;
  confidence: number;
  color: string;
};

const initialLayers: SourceLayer[] = [
  {
    id: 'l1',
    level: 1,
    title: '一级信源：官方原始发布核对',
    description: '调用增强分析接口，对输入内容做原文级别核验。',
    status: 'ready',
  },
  {
    id: 'l2',
    level: 2,
    title: '二级信源：权威媒体跨平台检索',
    description: '调用多平台搜索接口，核对媒体渠道传播与来源一致性。',
    status: 'ready',
  },
  {
    id: 'l3',
    level: 3,
    title: '三级信源：可信度综合分析',
    description: '调用跨平台可信度分析接口，生成证据链与综合评分。',
    status: 'ready',
  },
  {
    id: 'l4',
    level: 4,
    title: '四级信源：多Agent交叉复核',
    description: '调用多Agent分析接口，输出共识点与冲突点。',
    status: 'ready',
  },
];

export const ReportsScreen: React.FC = () => {
  const [topic, setTopic] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [layers, setLayers] = useState<SourceLayer[]>(initialLayers);
  const [credibilityScore, setCredibilityScore] = useState(0.5);
  const [evidenceNodes, setEvidenceNodes] = useState<EvidenceNode[]>([]);
  const [generatedDraft, setGeneratedDraft] = useState('');
  const [exportHint, setExportHint] = useState('');

  const completedCount = useMemo(
    () => layers.filter((item) => item.status === 'done').length,
    [layers]
  );

  const setLayerStatus = (id: string, status: LayerStatus, summary?: string) => {
    setLayers((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status, summary: summary || item.summary } : item))
    );
  };

  const buildDraft = (score: number, riskFlags: string[], consensus: string[]) => {
    const verdict = score >= 0.7 ? '认可' : '辟谣';
    const title = `${verdict}说明：关于“${topic}”的信息核验结论`;
    const lines = [
      `# ${title}`,
      '',
      `## 核验结论`,
      `- 综合可信度：${Math.round(score * 100)}%`,
      `- 结论类型：${verdict}`,
      '',
      '## 分层信源核验过程',
      ...layers.map((layer) => `- ${layer.title}：${layer.summary || '已执行'}`),
      '',
      '## 风险提示',
      ...(riskFlags.length > 0 ? riskFlags.map((flag) => `- ${flag}`) : ['- 暂无明显高风险标签']),
      '',
      '## 多方共识',
      ...(consensus.length > 0 ? consensus.map((item) => `- ${item}`) : ['- 暂无明确共识点']),
      '',
      '## 发布建议',
      verdict === '认可'
        ? '- 建议按“权威来源 + 证据链”方式发布认可文章。'
        : '- 建议按“谣言点拆解 + 官方依据”方式发布辟谣文章。',
    ];

    return lines.join('\n');
  };

  const runLayeredVerification = async () => {
    if (!topic.trim()) {
      Alert.alert('提示', '请先输入要核验的话题或声明');
      return;
    }

    setIsRunning(true);
    setLayers(initialLayers);
    setEvidenceNodes([]);
    setGeneratedDraft('');

    let score = 0.5;
    let riskFlags: string[] = [];
    let consensusPoints: string[] = [];

    try {
      // Layer 1
      setLayerStatus('l1', 'running');
      try {
        const layer1 = await verificationService.layer1OfficialAnalyze(topic, 'manual');
        const l1Score = layer1.reasoning_chain?.final_score || layer1.intel?.credibility_score;
        if (typeof l1Score === 'number') score = l1Score;
        setLayerStatus('l1', 'done', '已完成官方原文与逻辑推理核验');
      } catch (error: any) {
        setLayerStatus('l1', 'failed', error?.message || '一级信源核验失败');
      }

      // Layer 2
      setLayerStatus('l2', 'running');
      try {
        const layer2 = await verificationService.layer2MediaSearch(topic);
        const posts = layer2.total_posts || 0;
        const platforms = layer2.platform_count || 0;
        setLayerStatus('l2', 'done', `检索到${posts}条相关信息，覆盖${platforms}个平台`);
      } catch (error: any) {
        setLayerStatus('l2', 'failed', error?.message || '二级信源核验失败');
      }

      // Layer 3
      setLayerStatus('l3', 'running');
      try {
        const layer3 = await verificationService.layer3CredibilityAnalyze(topic);
        const reportScore = layer3.data?.credibility_score;
        if (typeof reportScore === 'number') score = reportScore;
        riskFlags = layer3.data?.risk_flags || [];

        const chain = layer3.data?.evidence_chain || [];
        const nodes: EvidenceNode[] = chain.slice(0, 6).map((item, index) => ({
          id: `ec-${index}`,
          label: item.step || item.description || `证据节点 ${index + 1}`,
          confidence: Math.max(0.5, score - index * 0.06),
          color: index % 2 === 0 ? theme.colors.primary.main : theme.colors.brand.success,
        }));
        setEvidenceNodes(
          nodes.length > 0
            ? nodes
            : [
                {
                  id: 'fallback-1',
                  label: '综合证据链节点',
                  confidence: score,
                  color: theme.colors.primary.main,
                },
              ]
        );

        setLayerStatus('l3', 'done', `综合可信度 ${Math.round(score * 100)}%`);
      } catch (error: any) {
        setLayerStatus('l3', 'failed', error?.message || '三级信源核验失败');
      }

      // Layer 4
      setLayerStatus('l4', 'running');
      try {
        const layer4 = await verificationService.layer4MultiAgentAnalyze(topic);
        const agentScore = layer4.data?.overall_credibility;
        if (typeof agentScore === 'number') {
          score = score * 0.6 + agentScore * 0.4;
        }
        consensusPoints = layer4.data?.consensus_points || [];
        riskFlags = [...new Set([...(riskFlags || []), ...(layer4.data?.risk_flags || [])])];
        setLayerStatus('l4', 'done', '多Agent复核完成，已融合跨平台共识/冲突信息');
      } catch (error: any) {
        setLayerStatus('l4', 'failed', error?.message || '四级信源核验失败');
      }

      setCredibilityScore(score);
      setGeneratedDraft(buildDraft(score, riskFlags, consensusPoints));
    } finally {
      setIsRunning(false);
    }
  };

  const handleSaveArticle = async () => {
    if (!generatedDraft.trim()) {
      Alert.alert('提示', '请先执行分层核验并生成草稿');
      return;
    }

    const kind = credibilityScore >= 0.7 ? 'approve' : 'refute';
    const titlePrefix = kind === 'approve' ? '认可说明' : '辟谣说明';

    await historyService.saveGeneratedArticle({
      title: `${titlePrefix}：${topic}`,
      topic,
      kind,
      credibility: credibilityScore,
      content: generatedDraft,
      sources: layers.map((layer) => layer.title),
    });

    const artifacts = documentExportService.buildNativeArtifacts({
      title: `${titlePrefix}：${topic}`,
      topic,
      verdict: kind === 'approve' ? '认可' : '辟谣',
      credibility: credibilityScore,
      content: generatedDraft,
      sources: layers.map((layer) => layer.title),
    });
    setExportHint(`已生成 ${artifacts.map((a) => a.format.toUpperCase()).join(' / ')} 导出结构`);

    Alert.alert('保存成功', '文章已保存到历史记录。');
  };

  const handleShowFormatMatrix = () => {
    const matrix = documentExportService.getFormatMatrix();
    const lines = matrix.map(
      (item) => `${item.format.toUpperCase()}：${item.available ? '可用' : '待后端支持'}（${item.note}）`
    );
    Alert.alert('导出格式支持', lines.join('\n'));
  };

  const getStatusColor = (status: LayerStatus) => {
    if (status === 'done') return theme.colors.status.true;
    if (status === 'running') return theme.colors.status.uncertain;
    if (status === 'failed') return theme.colors.status.false;
    return theme.colors.text.muted;
  };

  const getStatusText = (status: LayerStatus) => {
    if (status === 'done') return '已完成';
    if (status === 'running') return '核验中';
    if (status === 'failed') return '失败';
    return '待执行';
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />

      <View style={styles.header}>
        <Text style={styles.title}>验真报告</Text>
        <TouchableOpacity style={styles.headerAction}>
          <Ionicons name="sparkles-outline" size={20} color={theme.colors.text.secondary} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <CoreChatHeader compact />

        <Card style={styles.queryCard}>
          <Text style={styles.sectionTitle}>核验主题</Text>
          <TextInput
            value={topic}
            onChangeText={setTopic}
            placeholder="输入待核验的话题、声明或关键词"
            placeholderTextColor={theme.colors.text.placeholder}
            style={styles.topicInput}
          />
        </Card>

        <Card style={styles.scoreCard}>
          <View style={styles.scoreHeader}>
            <Text style={styles.sectionTitle}>当前可信度</Text>
            <CredibilityBadge score={credibilityScore} size="sm" />
          </View>
          <View style={styles.scoreRow}>
            <Text style={styles.scoreValue}>{Math.round(credibilityScore * 100)}%</Text>
            <Text style={styles.scoreHint}>已完成 {completedCount}/4 层核验</Text>
          </View>
          <Button
            title={isRunning ? '正在分层调用真实信源...' : '开始分层核验'}
            onPress={runLayeredVerification}
            loading={isRunning}
            style={styles.verifyButton}
          />
        </Card>

        <Card style={styles.layersCard}>
          <Text style={styles.sectionTitle}>分层信源调用状态</Text>
          {layers.map((layer) => (
            <View key={layer.id} style={styles.layerItem}>
              <View style={styles.layerTopRow}>
                <Text style={styles.layerTitle}>{layer.title}</Text>
                <Text style={[styles.layerStatus, { color: getStatusColor(layer.status) }]}>
                  {getStatusText(layer.status)}
                </Text>
              </View>
              <Text style={styles.layerDescription}>{layer.description}</Text>
              {layer.summary ? <Text style={styles.layerSummary}>{layer.summary}</Text> : null}
            </View>
          ))}
        </Card>

        <Card style={styles.mapCard}>
          <Text style={styles.sectionTitle}>证据链可视化</Text>
          <View style={styles.mapContainer}>
            {(evidenceNodes.length > 0
              ? evidenceNodes
              : [
                  {
                    id: 'placeholder',
                    label: '等待核验生成证据链',
                    confidence: 0,
                    color: theme.colors.border.default,
                  },
                ]
            ).map((node, index, list) => (
              <View key={node.id} style={styles.nodeWrap}>
                <View style={[styles.node, { borderColor: node.color }]}>
                  <Text style={styles.nodeLabel}>{node.label}</Text>
                  <Text style={styles.nodeConfidence}>
                    {node.confidence > 0 ? `${Math.round(node.confidence * 100)}%` : '--'}
                  </Text>
                </View>
                {index < list.length - 1 && <View style={styles.connector} />}
              </View>
            ))}
          </View>
        </Card>

        <Card style={styles.articleCard}>
          <Text style={styles.sectionTitle}>文章草稿（中文）</Text>
          <Text style={styles.draftPreview} numberOfLines={10}>
            {generatedDraft || '完成分层核验后会自动生成“辟谣/认可”草稿'}
          </Text>
          {exportHint ? <Text style={styles.exportHint}>{exportHint}</Text> : null}
          <Button title="查看导出格式支持" onPress={handleShowFormatMatrix} variant="outline" />
          <Button title="生成并保存到历史记录" onPress={handleSaveArticle} variant="outline" />
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.primary,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.light,
  },
  title: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.hero,
    fontWeight: '800',
  },
  headerAction: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: theme.colors.background.secondary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 110,
    gap: 12,
  },
  queryCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 10,
  },
  topicInput: {
    height: 42,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    borderRadius: theme.borderRadius.md,
    paddingHorizontal: 12,
    color: theme.colors.text.primary,
    backgroundColor: theme.colors.background.secondary,
    fontSize: theme.fontSize.base,
  },
  scoreCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 12,
  },
  scoreHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.lg,
    fontWeight: '700',
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 10,
  },
  scoreValue: {
    color: theme.colors.text.primary,
    fontSize: 42,
    fontWeight: '800',
  },
  scoreHint: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  verifyButton: {
    backgroundColor: theme.colors.brand.success,
  },
  layersCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 10,
  },
  layerItem: {
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    borderRadius: theme.borderRadius.md,
    padding: 10,
    gap: 4,
  },
  layerTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  layerTitle: {
    flex: 1,
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.base,
    fontWeight: '600',
  },
  layerStatus: {
    fontSize: theme.fontSize.sm,
    fontWeight: '600',
  },
  layerDescription: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.sm,
  },
  layerSummary: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.xs,
  },
  mapCard: {
    backgroundColor: theme.colors.background.tertiary,
  },
  mapContainer: {
    marginTop: 10,
  },
  nodeWrap: {
    alignItems: 'center',
  },
  node: {
    width: '100%',
    borderWidth: 1,
    borderRadius: theme.borderRadius.md,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: theme.colors.background.secondary,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  nodeLabel: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.base,
    fontWeight: '600',
  },
  nodeConfidence: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  connector: {
    width: 2,
    height: 14,
    backgroundColor: theme.colors.border.default,
  },
  articleCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 10,
  },
  draftPreview: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.base,
    lineHeight: 20,
    backgroundColor: theme.colors.background.secondary,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    borderRadius: theme.borderRadius.md,
    padding: 10,
  },
  exportHint: {
    color: theme.colors.status.true,
    fontSize: theme.fontSize.sm,
  },
});

export default ReportsScreen;
