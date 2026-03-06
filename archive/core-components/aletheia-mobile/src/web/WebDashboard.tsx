import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { analyzeEnhanced, buildCredibilityReport, searchAcrossPlatforms } from './client';
import type {
  CredibilityReport,
  EnhancedAnalyzeResponse,
  MultiPlatformSearchResponse,
  WebMode,
} from './types';

type SearchRow = {
  id: string;
  platform: string;
  title: string;
  summary: string;
  score: number;
};

const NAV_ITEMS: Array<{ key: WebMode; label: string; icon: string }> = [
  { key: 'search', label: 'Search', icon: '⌕' },
  { key: 'audit', label: '审核模式', icon: '✦' },
  { key: 'report', label: '检验报告', icon: '◫' },
];

const SOURCE_OPTIONS = [
  { label: '微博', value: 'weibo' },
  { label: 'Twitter', value: 'twitter' },
  { label: '小红书', value: 'xiaohongshu' },
  { label: '综合', value: 'mixed' },
];

function pickString(obj: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
}

function normalizeSearchRows(response: MultiPlatformSearchResponse | null): SearchRow[] {
  if (!response) {
    return [];
  }

  const rows: SearchRow[] = [];

  Object.entries(response.data).forEach(([platform, records]) => {
    records.forEach((record, index) => {
      const title = pickString(record, ['title', 'headline', 'name']) || `${platform} 内容 ${index + 1}`;
      const summary =
        pickString(record, ['content', 'text', 'description', 'snippet']) ||
        '未返回摘要，建议点开原文进一步核查上下文。';
      const metadata = (record.metadata || {}) as Record<string, unknown>;
      const likes = Number(metadata.likes || 0);
      const comments = Number(metadata.comments || 0);
      const shares = Number(metadata.shares || 0);
      const weighted = likes * 0.45 + comments * 0.35 + shares * 0.2;
      const score = Math.max(55, Math.min(97, Math.round(55 + weighted / 25)));

      rows.push({
        id: `${platform}-${index}`,
        platform,
        title,
        summary,
        score,
      });
    });
  });

  return rows;
}

function scoreColor(score: number) {
  if (score >= 85) return '#00D084';
  if (score >= 70) return '#FFB020';
  return '#FF5C7A';
}

function toPercent(value: number | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0;
  }

  if (value > 1) {
    return Math.round(value);
  }

  return Math.round(value * 100);
}

export const WebDashboard: React.FC = () => {
  const { width } = useWindowDimensions();
  const isCompact = width < 980;

  const [mode, setMode] = useState<WebMode>('audit');
  const [sourcePlatform, setSourcePlatform] = useState('mixed');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enhanced, setEnhanced] = useState<EnhancedAnalyzeResponse | null>(null);
  const [searchResult, setSearchResult] = useState<MultiPlatformSearchResponse | null>(null);
  const [report, setReport] = useState<CredibilityReport | null>(null);

  const searchRows = useMemo(() => normalizeSearchRows(searchResult), [searchResult]);

  const runAction = async () => {
    if (!input.trim()) {
      setError('请先输入要分析或搜索的内容');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (mode === 'audit') {
        const result = await analyzeEnhanced(input.trim(), sourcePlatform);
        setEnhanced(result);
        setSearchResult(null);
        setReport(null);
      }

      if (mode === 'search') {
        const result = await searchAcrossPlatforms(input.trim(), sourcePlatform);
        setSearchResult(result);
        setEnhanced(null);
        setReport(null);
      }

      if (mode === 'report') {
        const result = await buildCredibilityReport(input.trim(), sourcePlatform);
        setReport(result.data);
        setEnhanced(null);
        setSearchResult(null);
      }
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : '请求失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const modeTitle = {
    audit: '真相洞察引擎',
    search: 'Search',
    report: '核验报告',
  }[mode];

  const modeSubtitle = {
    audit: '追踪线索，基于交叉信源与多步推理完成可信度核验',
    search: '多平台实时搜索与证据拼接',
    report: '多平台交叉比对，输出结构化风险评估',
  }[mode];

  const evidence = enhanced?.reasoning_chain.steps?.slice(0, 3) ?? [];
  const credibilityScore =
    Number(enhanced?.intel.credibility_score) || Number(enhanced?.reasoning_chain.final_score) || 0;
  const credibilityLevel =
    (enhanced?.intel.credibility_level as string) || enhanced?.reasoning_chain.final_level || 'UNKNOWN';
  const reportEvidence = report?.evidence_chain ?? [];
  const reportFlags = report?.risk_flags ?? [];
  const platformStats = report?.platform_stats ? Object.entries(report.platform_stats) : [];

  return (
    <LinearGradient colors={['#050608', '#020305']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.root}>
      <View style={styles.frame}>
        {!isCompact && (
          <View style={styles.sidebar}>
            <Text style={styles.logo}>Aletheia</Text>
            <View style={styles.navWrap}>
              {NAV_ITEMS.map((item) => {
                const active = mode === item.key;
                return (
                  <Pressable
                    key={item.key}
                    onPress={() => setMode(item.key)}
                    style={[styles.navItem, active ? styles.navItemActive : null]}
                  >
                    <Text style={[styles.navIcon, active ? styles.navIconActive : null]}>{item.icon}</Text>
                    <Text style={[styles.navText, active ? styles.navTextActive : null]}>{item.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        )}

        <View style={styles.main}>
          <View style={styles.header}>
            <View style={styles.headerRight}>
              <View style={styles.avatar}><Text style={styles.avatarText}>AY</Text></View>
              <Pressable style={styles.loginBtn}><Text style={styles.loginText}>Login</Text></Pressable>
            </View>
          </View>

          {isCompact && (
            <View style={styles.mobileNav}>
              {NAV_ITEMS.map((item) => {
                const active = mode === item.key;
                return (
                  <Pressable
                    key={item.key}
                    onPress={() => setMode(item.key)}
                    style={[styles.mobileNavItem, active ? styles.mobileNavItemActive : null]}
                  >
                    <Text style={styles.mobileNavText}>{item.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}

          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner}>
            <Text style={styles.title}>{modeTitle}</Text>
            <Text style={styles.subtitle}>{modeSubtitle}</Text>

            {mode === 'audit' && enhanced && (
              <View style={styles.resultCard}>
                <View style={styles.resultTop}>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>核验结论</Text>
                    <Text style={[styles.tileValue, { color: scoreColor(toPercent(credibilityScore)) }]}> 
                      {toPercent(credibilityScore)}% · {credibilityLevel}
                    </Text>
                  </View>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>推理强度</Text>
                    <Text style={styles.tileValue}>{toPercent(enhanced.reasoning_chain.total_confidence)}%</Text>
                  </View>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>来源</Text>
                    <Text style={styles.tileValue}>{String(enhanced.intel.source_platform || sourcePlatform)}</Text>
                  </View>
                </View>
                <View style={styles.evidenceList}>
                  {evidence.map((item, index) => (
                    <Text style={styles.evidenceItem} key={`${item.stage}-${index}`}>
                      {item.stage}: {item.conclusion}
                    </Text>
                  ))}
                </View>
              </View>
            )}

            {mode === 'search' && searchRows.length > 0 && (
              <View style={styles.feedList}>
                {searchRows.map((row) => (
                  <View key={row.id} style={styles.feedRow}>
                    <View style={styles.feedBody}>
                      <Text style={styles.feedTitle}>{row.platform} · {row.title}</Text>
                      <Text style={styles.feedSummary} numberOfLines={2}>{row.summary}</Text>
                    </View>
                    <View style={[styles.feedScore, { borderColor: scoreColor(row.score) }]}>
                      <Text style={[styles.feedScoreText, { color: scoreColor(row.score) }]}>{row.score}%</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}

            {mode === 'report' && report && (
              <View style={styles.resultCard}>
                <View style={styles.resultTop}>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>可信度</Text>
                    <Text style={styles.tileValue}>{toPercent(report.credibility_score)}%</Text>
                  </View>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>等级</Text>
                    <Text style={styles.tileValue}>{report.credibility_level}</Text>
                  </View>
                  <View style={styles.tile}>
                    <Text style={styles.tileLabel}>覆盖平台</Text>
                    <Text style={styles.tileValue}>{report.summary.platform_count}</Text>
                  </View>
                </View>

                <View style={styles.reportGrid}>
                  <View style={styles.reportColumn}>
                    <Text style={styles.sectionLabel}>风险标签</Text>
                    <View style={styles.tagsWrap}>
                      {reportFlags.length > 0 ? (
                        reportFlags.map((tag) => (
                          <View key={tag} style={styles.tag}>
                            <Text style={styles.tagText}>{tag}</Text>
                          </View>
                        ))
                      ) : (
                        <Text style={styles.evidenceItem}>未发现高风险标签</Text>
                      )}
                    </View>

                    <Text style={styles.sectionLabel}>证据链</Text>
                    {reportEvidence.slice(0, 4).map((item, index) => (
                      <View key={`${item.step}-${index}`} style={styles.evidenceBlock}>
                        <Text style={styles.evidenceStep}>{item.step}</Text>
                        <Text style={styles.evidenceItem}>{item.description}</Text>
                      </View>
                    ))}
                    {reportEvidence.length === 0 && (
                      <Text style={styles.evidenceItem}>当前报告未返回证据链</Text>
                    )}
                  </View>

                  <View style={styles.reportColumn}>
                    <Text style={styles.sectionLabel}>平台统计</Text>
                    <View style={styles.statsList}>
                      {platformStats.slice(0, 4).map(([platform, stats]) => (
                        <View key={platform} style={styles.statsItem}>
                          <Text style={styles.statsPlatform}>{platform}</Text>
                          <Text style={styles.statsMeta}>帖子 {stats.post_count} · 互动 {stats.avg_engagement.toFixed(1)}</Text>
                        </View>
                      ))}
                      {platformStats.length === 0 && (
                        <Text style={styles.evidenceItem}>暂无平台统计</Text>
                      )}
                    </View>

                    <Text style={styles.sectionLabel}>摘要</Text>
                    <View style={styles.summaryPanel}>
                      <Text style={styles.summaryText}>总帖子 {report.summary.total_posts}</Text>
                      <Text style={styles.summaryText}>总互动 {report.summary.total_engagement}</Text>
                      <Text style={styles.summaryText}>新账号占比 {toPercent(report.summary.new_account_ratio)}%</Text>
                    </View>
                  </View>
                </View>
              </View>
            )}

            {error && <Text style={styles.errorText}>{error}</Text>}
          </ScrollView>

          <View style={styles.composer}>
            <Text style={styles.composerTitle}>问 Aletheia</Text>
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder="输入待验证内容、事件关键词或报告主题"
              placeholderTextColor="#6E7785"
              style={styles.input}
              multiline
              numberOfLines={2}
            />
            <View style={styles.actionRow}>
              <View style={styles.sourceRow}>
                {SOURCE_OPTIONS.map((option) => {
                  const active = option.value === sourcePlatform;
                  return (
                    <Pressable
                      key={option.value}
                      onPress={() => setSourcePlatform(option.value)}
                      style={[styles.sourceChip, active ? styles.sourceChipActive : null]}
                    >
                      <Text style={[styles.sourceChipText, active ? styles.sourceChipTextActive : null]}>
                        {option.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              <Pressable style={styles.primaryBtn} onPress={runAction}>
                {loading ? <ActivityIndicator color="#FFFFFF" size="small" /> : <Text style={styles.primaryBtnText}>执行</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </View>
    </LinearGradient>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    padding: 16,
  },
  frame: {
    flex: 1,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#1A1F27',
    overflow: 'hidden',
    flexDirection: 'row',
    backgroundColor: '#04070B',
  },
  sidebar: {
    width: 210,
    borderRightWidth: 1,
    borderRightColor: '#1A1F27',
    padding: 14,
    backgroundColor: '#070C14',
  },
  logo: {
    color: '#F4F7FB',
    fontSize: 17,
    fontWeight: '700',
    marginBottom: 24,
  },
  navWrap: {
    gap: 8,
  },
  navItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: 8,
  },
  navItemActive: {
    backgroundColor: '#10253E',
  },
  navIcon: {
    color: '#7A8798',
    fontSize: 13,
  },
  navIconActive: {
    color: '#76B8FF',
  },
  navText: {
    color: '#8A96A9',
    fontSize: 13,
  },
  navTextActive: {
    color: '#D6E8FF',
    fontWeight: '600',
  },
  main: {
    flex: 1,
  },
  header: {
    height: 56,
    borderBottomWidth: 1,
    borderBottomColor: '#141A22',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  headerRight: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 10,
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#111C2A',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: '#D8E5F7',
    fontSize: 10,
    fontWeight: '700',
  },
  loginBtn: {
    backgroundColor: '#0F1724',
    borderColor: '#1E2B3D',
    borderWidth: 1,
    borderRadius: 7,
    paddingVertical: 6,
    paddingHorizontal: 11,
  },
  loginText: {
    color: '#E5EFFD',
    fontSize: 11,
    fontWeight: '600',
  },
  mobileNav: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#141A22',
  },
  mobileNavItem: {
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: '#0B121D',
  },
  mobileNavItemActive: {
    backgroundColor: '#10253E',
  },
  mobileNavText: {
    color: '#C8D7EC',
    fontSize: 12,
  },
  content: {
    flex: 1,
  },
  contentInner: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 180,
  },
  title: {
    color: '#F6FBFF',
    fontSize: 35,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  subtitle: {
    color: '#8E9AB0',
    fontSize: 12,
    marginTop: 6,
    marginBottom: 14,
  },
  resultCard: {
    borderWidth: 1,
    borderColor: '#1C2A3A',
    borderRadius: 12,
    backgroundColor: '#0A1018',
    padding: 12,
    marginBottom: 14,
  },
  resultTop: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  tile: {
    flex: 1,
    minWidth: 180,
    backgroundColor: '#0C1420',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1B2735',
    padding: 10,
  },
  tileLabel: {
    color: '#7F8CA0',
    fontSize: 11,
    marginBottom: 4,
  },
  tileValue: {
    color: '#F5FAFF',
    fontSize: 18,
    fontWeight: '700',
  },
  evidenceList: {
    marginTop: 10,
    gap: 8,
  },
  evidenceItem: {
    color: '#C5D2E6',
    fontSize: 12,
    lineHeight: 18,
  },
  evidenceBlock: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1D2C3E',
    backgroundColor: '#0B1420',
    padding: 9,
    marginBottom: 8,
  },
  evidenceStep: {
    color: '#DCEBFF',
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 4,
  },
  feedList: {
    gap: 8,
  },
  feedRow: {
    borderWidth: 1,
    borderColor: '#1A293B',
    borderRadius: 10,
    backgroundColor: '#0A111B',
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  feedBody: {
    flex: 1,
  },
  feedTitle: {
    color: '#E6EEF9',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 4,
  },
  feedSummary: {
    color: '#8FA2BA',
    fontSize: 12,
    lineHeight: 17,
  },
  feedScore: {
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  feedScoreText: {
    fontSize: 11,
    fontWeight: '700',
  },
  sectionLabel: {
    color: '#A8BCD8',
    fontSize: 12,
    marginTop: 12,
    marginBottom: 8,
  },
  reportGrid: {
    marginTop: 10,
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  reportColumn: {
    flex: 1,
    minWidth: 260,
  },
  statsList: {
    gap: 8,
  },
  statsItem: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#22364D',
    backgroundColor: '#0A1523',
    paddingVertical: 8,
    paddingHorizontal: 10,
  },
  statsPlatform: {
    color: '#E6F1FF',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'capitalize',
    marginBottom: 2,
  },
  statsMeta: {
    color: '#A7BDD8',
    fontSize: 11,
  },
  summaryPanel: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1D3047',
    backgroundColor: '#0A1420',
    padding: 10,
    gap: 6,
  },
  summaryText: {
    color: '#D4E3F7',
    fontSize: 12,
  },
  tagsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tag: {
    borderWidth: 1,
    borderColor: '#28405E',
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 9,
  },
  tagText: {
    color: '#A9C9EC',
    fontSize: 11,
    fontWeight: '600',
  },
  errorText: {
    color: '#FF6D8C',
    fontSize: 12,
    marginTop: 12,
  },
  composer: {
    position: 'absolute',
    left: 16,
    right: 16,
    bottom: 14,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#1B2A3C',
    backgroundColor: '#11161E',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  composerTitle: {
    color: '#E8F2FF',
    fontSize: 13,
    fontWeight: '600',
  },
  input: {
    color: '#EAF4FF',
    fontSize: 13,
    minHeight: 48,
    textAlignVertical: 'top',
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  sourceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    flex: 1,
  },
  sourceChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#26364D',
    paddingVertical: 5,
    paddingHorizontal: 9,
    backgroundColor: '#0C131D',
  },
  sourceChipActive: {
    borderColor: '#2A67C7',
    backgroundColor: '#12325A',
  },
  sourceChipText: {
    color: '#A4B3C7',
    fontSize: 11,
  },
  sourceChipTextActive: {
    color: '#DCECFF',
  },
  primaryBtn: {
    height: 34,
    borderRadius: 8,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1251C9',
    minWidth: 72,
  },
  primaryBtnText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
});

export default WebDashboard;
