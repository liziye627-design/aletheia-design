/**
 * Authoritative Sources Screen - 权威信源
 * 展示媒体/政务高可信度信息（红头文件、官方发布）
 */

import React, { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  SafeAreaView,
  TouchableOpacity,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';

import { CoreChatHeader, Card, CredibilityBadge } from '../components';
import { theme } from '../utils/theme';

// 权威信源类型
interface AuthoritativeSource {
  id: string;
  title: string;
  source: string;
  sourceType: 'government' | 'media' | 'official';
  publishedAt: string;
  credibilityScore: number;
  summary: string;
  imageUrl?: string;
  documentType?: string; // 红头文件, 新闻发布, 政策解读等
  verified: boolean;
}

// Mock数据
const mockSources: AuthoritativeSource[] = [
  {
    id: '1',
    title: '国务院关于2026年经济工作的指导意见',
    source: '中华人民共和国国务院',
    sourceType: 'government',
    publishedAt: '2026-02-08T10:00:00Z',
    credibilityScore: 0.98,
    summary: '国务院发布2026年经济工作重点，强调稳增长、促改革、调结构...',
    documentType: '红头文件',
    verified: true,
  },
  {
    id: '2',
    title: '新华社权威发布：关于近期网络谣言的澄清说明',
    source: '新华社',
    sourceType: 'media',
    publishedAt: '2026-02-07T14:30:00Z',
    credibilityScore: 0.95,
    summary: '针对近期网络流传的多条不实信息，新华社发布权威澄清...',
    documentType: '辟谣声明',
    verified: true,
  },
  {
    id: '3',
    title: '教育部2026年高考改革方案正式公布',
    source: '中华人民共和国教育部',
    sourceType: 'government',
    publishedAt: '2026-02-06T09:00:00Z',
    credibilityScore: 0.97,
    summary: '教育部正式发布2026年高考改革方案，包含多项重要调整...',
    documentType: '政策文件',
    verified: true,
  },
  {
    id: '4',
    title: '人民日报评论员文章：坚持高质量发展不动摇',
    source: '人民日报',
    sourceType: 'media',
    publishedAt: '2026-02-05T08:00:00Z',
    credibilityScore: 0.94,
    summary: '本报评论员文章深入解读当前经济形势和发展方向...',
    documentType: '评论文章',
    verified: true,
  },
  {
    id: '5',
    title: '卫生健康委关于春季传染病防控的通知',
    source: '国家卫生健康委员会',
    sourceType: 'government',
    publishedAt: '2026-02-04T11:00:00Z',
    credibilityScore: 0.96,
    summary: '国家卫健委发布春季传染病防控工作指导意见...',
    documentType: '通知公告',
    verified: true,
  },
];

export const FeedsScreen: React.FC = () => {
  const [sources, setSources] = useState<AuthoritativeSource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'government' | 'media'>('all');

  useEffect(() => {
    fetchSources();
  }, []);

  const fetchSources = async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 800));
      setSources(mockSources);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleRefresh = useCallback(() => {
    fetchSources(true);
  }, []);

  const filteredSources = sources.filter(source => {
    if (selectedFilter === 'all') return true;
    return source.sourceType === selectedFilter;
  });

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'government':
        return 'business';
      case 'media':
        return 'newspaper';
      case 'official':
        return 'ribbon';
      default:
        return 'document';
    }
  };

  const getSourceColor = (sourceType: string) => {
    switch (sourceType) {
      case 'government':
        return '#E53935'; // 红色 - 政务
      case 'media':
        return '#1E88E5'; // 蓝色 - 媒体
      case 'official':
        return '#43A047'; // 绿色 - 官方
      default:
        return theme.colors.text.muted;
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const renderItem = ({ item }: { item: AuthoritativeSource }) => (
    <TouchableOpacity onPress={() => {}}>
      <Card style={styles.sourceCard}>
        {/* Header */}
        <View style={styles.cardHeader}>
          <View style={styles.sourceInfo}>
            <View style={[styles.sourceIcon, { backgroundColor: getSourceColor(item.sourceType) + '20' }]}>
              <Ionicons 
                name={getSourceIcon(item.sourceType) as any} 
                size={16} 
                color={getSourceColor(item.sourceType)} 
              />
            </View>
            <View>
              <Text style={styles.sourceName}>{item.source}</Text>
              <Text style={styles.sourceDate}>{formatDate(item.publishedAt)}</Text>
            </View>
          </View>
          {item.verified && (
            <View style={styles.verifiedBadge}>
              <Ionicons name="checkmark-circle" size={14} color={theme.colors.status.true} />
              <Text style={styles.verifiedText}>已验证</Text>
            </View>
          )}
        </View>

        {/* Document Type Tag */}
        {item.documentType && (
          <View style={[styles.documentTag, { backgroundColor: getSourceColor(item.sourceType) + '15' }]}>
            <Text style={[styles.documentTagText, { color: getSourceColor(item.sourceType) }]}>
              {item.documentType}
            </Text>
          </View>
        )}

        {/* Title */}
        <Text style={styles.sourceTitle} numberOfLines={2}>
          {item.title}
        </Text>

        {/* Summary */}
        <Text style={styles.sourceSummary} numberOfLines={2}>
          {item.summary}
        </Text>

        {/* Footer */}
        <View style={styles.cardFooter}>
          <CredibilityBadge score={item.credibilityScore} size="sm" />
          <View style={styles.footerActions}>
            <TouchableOpacity style={styles.actionButton}>
              <Ionicons name="bookmark-outline" size={18} color={theme.colors.text.muted} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.actionButton}>
              <Ionicons name="share-outline" size={18} color={theme.colors.text.muted} />
            </TouchableOpacity>
          </View>
        </View>
      </Card>
    </TouchableOpacity>
  );

  const renderHeader = () => (
    <View>
      {/* Core Chat Header - 核心对话框 */}
      <CoreChatHeader compact />

      {/* Filter Tabs */}
      <View style={styles.filterContainer}>
        <TouchableOpacity
          style={[styles.filterTab, selectedFilter === 'all' && styles.filterTabActive]}
          onPress={() => setSelectedFilter('all')}
        >
          <Text style={[styles.filterText, selectedFilter === 'all' && styles.filterTextActive]}>
            全部
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterTab, selectedFilter === 'government' && styles.filterTabActive]}
          onPress={() => setSelectedFilter('government')}
        >
          <Ionicons 
            name="business" 
            size={14} 
            color={selectedFilter === 'government' ? theme.colors.text.primary : theme.colors.text.muted} 
          />
          <Text style={[styles.filterText, selectedFilter === 'government' && styles.filterTextActive]}>
            政务
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterTab, selectedFilter === 'media' && styles.filterTabActive]}
          onPress={() => setSelectedFilter('media')}
        >
          <Ionicons 
            name="newspaper" 
            size={14} 
            color={selectedFilter === 'media' ? theme.colors.text.primary : theme.colors.text.muted} 
          />
          <Text style={[styles.filterText, selectedFilter === 'media' && styles.filterTextActive]}>
            媒体
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderEmpty = () => {
    if (isLoading) return null;
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="shield-checkmark-outline" size={64} color={theme.colors.text.muted} />
        <Text style={styles.emptyText}>暂无权威信源</Text>
        <Text style={styles.emptySubtext}>下拉刷新获取最新内容</Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>权威信源</Text>
        <TouchableOpacity style={styles.searchButton}>
          <Ionicons name="filter-outline" size={22} color={theme.colors.text.secondary} />
        </TouchableOpacity>
      </View>

      {/* Content */}
      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary.main} />
        </View>
      ) : (
        <FlatList
          data={filteredSources}
          renderItem={renderItem}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          ListHeaderComponent={renderHeader}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor={theme.colors.primary.main}
              colors={[theme.colors.primary.main]}
            />
          }
          ListEmptyComponent={renderEmpty}
          showsVerticalScrollIndicator={false}
        />
      )}
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
  searchButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: theme.colors.background.secondary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  filterTab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: theme.borderRadius.full,
    backgroundColor: theme.colors.background.secondary,
  },
  filterTabActive: {
    backgroundColor: theme.colors.brand.success,
  },
  filterText: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
    fontWeight: '500',
  },
  filterTextActive: {
    color: theme.colors.text.primary,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 100,
  },
  separator: {
    height: 12,
  },
  sourceCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 10,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sourceInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  sourceIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sourceName: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.sm,
    fontWeight: '600',
  },
  sourceDate: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.xs,
  },
  verifiedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: theme.borderRadius.sm,
    backgroundColor: theme.colors.status.true + '15',
  },
  verifiedText: {
    color: theme.colors.status.true,
    fontSize: theme.fontSize.xs,
    fontWeight: '500',
  },
  documentTag: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: theme.borderRadius.xs,
  },
  documentTagText: {
    fontSize: theme.fontSize.xs,
    fontWeight: '600',
  },
  sourceTitle: {
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.lg,
    fontWeight: '700',
    lineHeight: 22,
  },
  sourceSummary: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.base,
    lineHeight: 20,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  footerActions: {
    flexDirection: 'row',
    gap: 8,
  },
  actionButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: theme.colors.background.elevated,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
    gap: 12,
  },
  emptyText: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xl,
    fontWeight: '600',
  },
  emptySubtext: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.base,
  },
});

export default FeedsScreen;
