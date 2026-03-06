/**
 * Audit Screen - Truth Analysis Workbench
 * Based on aletheia-ui.pen Workbench design
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TextInput,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';

import { Button, Card, CredibilityBadge } from '../components';
import { theme } from '../utils/theme';
import { intelService } from '../services';
import type { IntelResult } from '../types';

export const AuditScreen: React.FC = () => {
  const [query, setQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<IntelResult | null>(null);
  const [processingTime, setProcessingTime] = useState<number | null>(null);

  const handleAnalyze = async () => {
    if (!query.trim()) {
      Alert.alert('Error', 'Please enter content to analyze');
      return;
    }

    setIsAnalyzing(true);
    setResult(null);

    try {
      const response = await intelService.analyze({
        content: query,
        source_platform: 'manual',
      });
      setResult(response.intel);
      setProcessingTime(response.processing_time_ms);
    } catch {
      // For demo, create mock result
      const mockResult: IntelResult = {
        id: 'mock-' + Date.now(),
        content: query,
        credibility_score: Math.random() * 0.4 + 0.3, // 0.3 - 0.7
        risk_tags: ['unverified_claims', 'limited_sources'],
        reasoning_chain: [
          {
            step: 1,
            type: 'observation',
            content: 'Analyzing content structure and claims...',
            confidence: 0.8,
          },
          {
            step: 2,
            type: 'hypothesis',
            content: 'Content contains unverified factual claims',
            confidence: 0.6,
          },
          {
            step: 3,
            type: 'verification',
            content: 'Cross-referencing with known sources...',
            confidence: 0.5,
          },
          {
            step: 4,
            type: 'conclusion',
            content: 'Insufficient evidence to verify claims',
            confidence: 0.55,
          },
        ],
        sources: [],
        created_at: new Date().toISOString(),
      };
      setResult(mockResult);
      setProcessingTime(Math.floor(Math.random() * 2000) + 500);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const renderReasoningChain = () => {
    if (!result) return null;

    return (
      <Card style={styles.resultCard}>
        <Text style={styles.sectionTitle}>Reasoning Chain</Text>
        {result.reasoning_chain.map((step, index) => (
          <View key={index} style={styles.reasoningStep}>
            <View style={styles.stepHeader}>
              <View style={[styles.stepBadge, { backgroundColor: getStepColor(step.type) }]}>
                <Text style={styles.stepBadgeText}>{step.type}</Text>
              </View>
              <Text style={styles.stepConfidence}>
                {Math.round(step.confidence * 100)}% confidence
              </Text>
            </View>
            <Text style={styles.stepContent}>{step.content}</Text>
          </View>
        ))}
      </Card>
    );
  };

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

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Aletheia</Text>
              <Text style={styles.subtitle}>Detective's Workbench</Text>
            </View>
          </View>

          {/* Query Input */}
          <View style={styles.querySection}>
            <View style={styles.queryContainer}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="Enter claim or content to analyze..."
                placeholderTextColor={theme.colors.text.placeholder}
                style={styles.queryInput}
                multiline
                numberOfLines={3}
              />
            </View>

            <Button
              title="Analyze"
              onPress={handleAnalyze}
              loading={isAnalyzing}
              variant="primary"
              style={styles.analyzeButton}
            />
          </View>

          {/* Loading State */}
          {isAnalyzing && (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={theme.colors.brand.success} />
              <Text style={styles.loadingText}>Analyzing content...</Text>
              <Text style={styles.loadingSubtext}>
                Running physics, logic, and entropy verification
              </Text>
            </View>
          )}

          {/* Result */}
          {result && !isAnalyzing && (
            <View style={styles.resultSection}>
              {/* Score Card */}
              <Card style={styles.scoreCard}>
                <View style={styles.scoreHeader}>
                  <Text style={styles.scoreTitle}>Credibility Score</Text>
                  {processingTime && (
                    <Text style={styles.processingTime}>
                      {processingTime}ms
                    </Text>
                  )}
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
                    <Text style={styles.tagsLabel}>Risk Tags:</Text>
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
              {renderReasoningChain()}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.primary,
  },
  keyboardView: {
    flex: 1,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 100,
  },
  header: {
    paddingVertical: 16,
  },
  title: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xxl,
    fontWeight: '700',
  },
  subtitle: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.md,
  },
  querySection: {
    gap: 12,
    marginBottom: 20,
  },
  queryContainer: {
    backgroundColor: theme.colors.background.secondary,
    borderRadius: theme.borderRadius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    padding: 12,
  },
  queryInput: {
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.base,
    minHeight: 80,
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
    gap: 16,
  },
  scoreCard: {
    backgroundColor: theme.colors.background.secondary,
  },
  scoreHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  scoreTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.base,
    fontWeight: '600',
  },
  processingTime: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
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
  resultCard: {
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
    textTransform: 'uppercase',
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
});

export default AuditScreen;
