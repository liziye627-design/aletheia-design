/**
 * History Screen - 历史记录
 * 读取真实存储（后端优先，失败回落本地）
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { Card } from '../components';
import { historyService } from '../services';
import { theme } from '../utils/theme';
import type { GeneratedArticleRecord } from '../types';

export const HistoryScreen: React.FC = () => {
  const navigation = useNavigation();
  const [items, setItems] = useState<GeneratedArticleRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const records = await historyService.getHistoryArticles();
      setItems(records);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatDate = (iso: string) => {
    const date = new Date(iso);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const renderItem = ({ item }: { item: GeneratedArticleRecord }) => {
    const color = item.kind === 'refute' ? theme.colors.status.false : theme.colors.status.true;
    const label = item.kind === 'refute' ? '辟谣文' : '认可文';

    return (
      <TouchableOpacity onPress={() => {}}>
        <Card style={styles.itemCard}>
          <View style={styles.topRow}>
            <View style={[styles.kindTag, { backgroundColor: color + '22' }]}>
              <Text style={[styles.kindText, { color }]}>{label}</Text>
            </View>
            <Text style={styles.dateText}>{formatDate(item.createdAt)}</Text>
          </View>
          <Text style={styles.titleText} numberOfLines={2}>
            {item.title}
          </Text>
          <Text style={styles.topicText}>{item.topic}</Text>
          <View style={styles.bottomRow}>
            <Text style={styles.credibilityText}>可信度 {Math.round(item.credibility * 100)}%</Text>
            <Ionicons name="chevron-forward" size={16} color={theme.colors.text.muted} />
          </View>
        </Card>
      </TouchableOpacity>
    );
  };

  const renderEmpty = () => {
    if (isLoading) return null;
    return (
      <View style={styles.emptyWrap}>
        <Ionicons name="document-text-outline" size={56} color={theme.colors.text.muted} />
        <Text style={styles.emptyTitle}>暂无历史记录</Text>
        <Text style={styles.emptySubTitle}>先去“验真报告”执行一次分层核验并保存文章</Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />

      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
          <Ionicons name="arrow-back" size={20} color={theme.colors.text.secondary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>历史记录</Text>
        <View style={styles.backButton} />
      </View>

      {isLoading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="large" color={theme.colors.primary.main} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          renderItem={renderItem}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={() => fetchData(true)}
              tintColor={theme.colors.primary.main}
            />
          }
          ListEmptyComponent={renderEmpty}
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
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.light,
  },
  backButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: theme.colors.background.secondary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xxl,
    fontWeight: '700',
  },
  loadingWrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    paddingBottom: 40,
  },
  separator: {
    height: 10,
  },
  itemCard: {
    backgroundColor: theme.colors.background.tertiary,
    gap: 8,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  kindTag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: theme.borderRadius.sm,
  },
  kindText: {
    fontSize: theme.fontSize.xs,
    fontWeight: '700',
  },
  dateText: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  titleText: {
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.lg,
    fontWeight: '700',
    lineHeight: 20,
  },
  topicText: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.sm,
  },
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  credibilityText: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  emptyWrap: {
    alignItems: 'center',
    paddingTop: 100,
    gap: 10,
  },
  emptyTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xl,
    fontWeight: '700',
  },
  emptySubTitle: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.base,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
});

export default HistoryScreen;
