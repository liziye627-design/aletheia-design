/**
 * Core Chat Header - AI驱动的谣言鉴定对话框
 * 作为所有Tab共享的头部核心功能入口
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { theme } from '../utils/theme';
import { Card } from './Card';
import { Button } from './Button';
import { CredibilityBadge } from './CredibilityBadge';
import { intelService } from '../services';
import type { IntelResult } from '../types';

interface CoreChatHeaderProps {
  compact?: boolean;
  onAnalysisComplete?: (result: IntelResult) => void;
}

export const CoreChatHeader: React.FC<CoreChatHeaderProps> = ({
  compact = false,
  onAnalysisComplete,
}) => {
  const [query, setQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [result, setResult] = useState<IntelResult | null>(null);

  const handleAnalyze = async () => {
    if (!query.trim()) return;

    setIsAnalyzing(true);
    setResult(null);

    try {
      const response = await intelService.analyze({
        content: query,
        source_platform: 'manual',
      });
      setResult(response.intel);
      onAnalysisComplete?.(response.intel);
    } catch {
      // Mock result for demo
      const mockResult: IntelResult = {
        id: 'mock-' + Date.now(),
        content: query,
        credibility_score: Math.random() * 0.4 + 0.3,
        risk_tags: ['unverified_claims', 'limited_sources'],
        reasoning_chain: [
          {
            step: 1,
            type: 'observation',
            content: '正在分析内容结构和声明...',
            confidence: 0.8,
          },
          {
            step: 2,
            type: 'hypothesis',
            content: '内容包含未经验证的事实声明',
            confidence: 0.6,
          },
          {
            step: 3,
            type: 'verification',
            content: '与已知信源进行交叉验证...',
            confidence: 0.5,
          },
          {
            step: 4,
            type: 'conclusion',
            content: '证据不足以验证相关声明',
            confidence: 0.55,
          },
        ],
        sources: [],
        created_at: new Date().toISOString(),
      };
      setResult(mockResult);
      onAnalysisComplete?.(mockResult);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleOpenModal = () => {
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setQuery('');
    setResult(null);
  };

  // Compact mode - just shows a search bar that opens modal
  if (compact) {
    return (
      <View style={styles.compactContainer}>
        <TouchableOpacity style={styles.compactInput} onPress={handleOpenModal}>
          <Ionicons name="search-outline" size={20} color={theme.colors.text.muted} />
          <Text style={styles.compactPlaceholder}>输入待验证的内容...</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.compactButton} onPress={handleOpenModal}>
          <Ionicons name="shield-checkmark" size={20} color={theme.colors.brand.success} />
        </TouchableOpacity>

        <Modal
          visible={showModal}
          animationType="slide"
          presentationStyle="pageSheet"
          onRequestClose={handleCloseModal}
        >
          <FullChatView
            query={query}
            setQuery={setQuery}
            isAnalyzing={isAnalyzing}
            result={result}
            onAnalyze={handleAnalyze}
            onClose={handleCloseModal}
          />
        </Modal>
      </View>
    );
  }

  // Full mode - shows the complete chat interface
  return (
    <FullChatView
      query={query}
      setQuery={setQuery}
      isAnalyzing={isAnalyzing}
      result={result}
      onAnalyze={handleAnalyze}
      onClose={() => {}}
      embedded
    />
  );
};

interface FullChatViewProps {
  query: string;
  setQuery: (q: string) => void;
  isAnalyzing: boolean;
  result: IntelResult | null;
  onAnalyze: () => void;
  onClose: () => void;
  embedded?: boolean;
}

const FullChatView: React.FC<FullChatViewProps> = ({
  query,
  setQuery,
  isAnalyzing,
  result,
  onAnalyze,
  onClose,
  embedded = false,
}) => {
  const getStepColor = (type: string) => {
    switch (type) {
      case 'observation':
        return theme.colors.primary.main;
      case 'hypothesis':
        return theme.colors.status.uncertain;
      case 'verification':
        return theme.colors.status.true;
      case 'conclusion':
        return theme.colors.brand.success;
      default:
        return theme.colors.text.muted;
    }
  };

  const getStepLabel = (type: string) => {
    switch (type) {
      case 'observation':
        return '观察';
      case 'hypothesis':
        return '假设';
      case 'verification':
        return '验证';
      case 'conclusion':
        return '结论';
      default:
        return type;
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={[styles.fullContainer, embedded && styles.embeddedContainer]}
    >
      {/* Header */}
      {!embedded && (
        <View style={styles.modalHeader}>
          <View>
            <Text style={styles.modalTitle}>Aletheia</Text>
            <Text style={styles.modalSubtitle}>AI谣言鉴定引擎</Text>
          </View>
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Ionicons name="close" size={24} color={theme.colors.text.secondary} />
          </TouchableOpacity>
        </View>
      )}

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Input Section */}
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>输入待验证内容</Text>
          <View style={styles.inputContainer}>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="粘贴文章、链接或输入待核验的声明..."
              placeholderTextColor={theme.colors.text.placeholder}
              style={styles.textInput}
              multiline
              numberOfLines={4}
            />
          </View>

          <Button
            title={isAnalyzing ? '分析中...' : '开始深度核验'}
            onPress={onAnalyze}
            loading={isAnalyzing}
            variant="primary"
            style={styles.analyzeButton}
          />
        </View>

        {/* Loading State */}
        {isAnalyzing && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={theme.colors.brand.success} />
            <Text style={styles.loadingText}>正在分析内容...</Text>
            <Text style={styles.loadingSubtext}>
              执行物理验证、逻辑验证、熵分析...
            </Text>
          </View>
        )}

        {/* Result */}
        {result && !isAnalyzing && (
          <View style={styles.resultSection}>
            {/* Score Card */}
            <Card style={styles.scoreCard}>
              <View style={styles.scoreHeader}>
                <Text style={styles.scoreTitle}>可信度评分</Text>
              </View>
              
              <View style={styles.scoreRow}>
                <Text style={styles.scoreValue}>
                  {Math.round(result.credibility_score * 100)}%
                </Text>
                <CredibilityBadge score={result.credibility_score} size="lg" />
              </View>

              {/* Risk Tags */}
              {result.risk_tags.length > 0 && (
                <View style={styles.tagsSection}>
                  <Text style={styles.tagsLabel}>风险标签:</Text>
                  <View style={styles.tagsContainer}>
                    {result.risk_tags.map((tag, index) => (
                      <View key={index} style={styles.tag}>
                        <Text style={styles.tagText}>{tag.replace(/_/g, ' ')}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}
            </Card>

            {/* Reasoning Chain */}
            <Card style={styles.reasoningCard}>
              <Text style={styles.sectionTitle}>推理链条</Text>
              {result.reasoning_chain.map((step, index) => (
                <View key={index} style={styles.reasoningStep}>
                  <View style={styles.stepHeader}>
                    <View style={[styles.stepBadge, { backgroundColor: getStepColor(step.type) }]}>
                      <Text style={styles.stepBadgeText}>{getStepLabel(step.type)}</Text>
                    </View>
                    <Text style={styles.stepConfidence}>
                      置信度 {Math.round(step.confidence * 100)}%
                    </Text>
                  </View>
                  <Text style={styles.stepContent}>{step.content}</Text>
                </View>
              ))}
            </Card>

            {/* Generate Report Button */}
            <Button
              title="生成验真报告"
              onPress={() => {}}
              variant="outline"
              style={styles.reportButton}
            />
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  // Compact mode styles
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.background.secondary,
    borderRadius: theme.borderRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 10,
    marginHorizontal: 16,
    marginVertical: 8,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
  },
  compactInput: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  compactPlaceholder: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.base,
  },
  compactButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.background.elevated,
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Full mode styles
  fullContainer: {
    flex: 1,
    backgroundColor: theme.colors.background.primary,
  },
  embeddedContainer: {
    paddingTop: 0,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.default,
  },
  modalTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xxl,
    fontWeight: '700',
  },
  modalSubtitle: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.md,
  },
  closeButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: theme.colors.background.secondary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  inputSection: {
    gap: 12,
  },
  inputLabel: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.lg,
    fontWeight: '600',
  },
  inputContainer: {
    backgroundColor: theme.colors.background.secondary,
    borderRadius: theme.borderRadius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    padding: 12,
  },
  textInput: {
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.base,
    minHeight: 100,
    textAlignVertical: 'top',
  },
  analyzeButton: {
    backgroundColor: theme.colors.brand.success,
  },
  loadingContainer: {
    alignItems: 'center',
    paddingVertical: 40,
    gap: 12,
  },
  loadingText: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xl,
    fontWeight: '600',
  },
  loadingSubtext: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.base,
  },
  resultSection: {
    marginTop: 20,
    gap: 16,
  },
  scoreCard: {
    backgroundColor: theme.colors.background.secondary,
  },
  scoreHeader: {
    marginBottom: 16,
  },
  scoreTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.base,
    fontWeight: '600',
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  scoreValue: {
    color: theme.colors.text.primary,
    fontSize: 48,
    fontWeight: '800',
  },
  tagsSection: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border.default,
  },
  tagsLabel: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
    marginBottom: 8,
  },
  tagsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tag: {
    backgroundColor: theme.colors.background.elevated,
    borderRadius: theme.borderRadius.sm,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: theme.colors.status.uncertain,
  },
  tagText: {
    color: theme.colors.status.uncertain,
    fontSize: theme.fontSize.sm,
    textTransform: 'capitalize',
  },
  reasoningCard: {
    backgroundColor: theme.colors.background.secondary,
  },
  sectionTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.base,
    fontWeight: '600',
    marginBottom: 16,
  },
  reasoningStep: {
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.default,
  },
  stepHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  stepBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: theme.borderRadius.xs,
  },
  stepBadgeText: {
    color: '#FFFFFF',
    fontSize: theme.fontSize.xs,
    fontWeight: '600',
  },
  stepConfidence: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  stepContent: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.base,
    lineHeight: 20,
  },
  reportButton: {
    borderColor: theme.colors.brand.success,
  },
});

export default CoreChatHeader;
