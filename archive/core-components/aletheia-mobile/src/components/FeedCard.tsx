/**
 * FeedCard Component - News/feed item card
 */

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { theme } from '../utils/theme';
import { CredibilityBadge } from './CredibilityBadge';
import type { FeedItem } from '../types';

interface FeedCardProps {
  item: FeedItem;
  onPress: () => void;
}

export const FeedCard: React.FC<FeedCardProps> = ({ item, onPress }) => {
  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    
    return date.toLocaleDateString();
  };

  const getRiskTagColor = (tag: string) => {
    if (tag.includes('misinformation') || tag.includes('false')) {
      return theme.colors.status.false;
    }
    if (tag.includes('unverified') || tag.includes('disputed')) {
      return theme.colors.status.uncertain;
    }
    return theme.colors.text.muted;
  };

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.8}>
      <View style={styles.card}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.source}>
            {item.source} · {formatTime(item.published_at)}
          </Text>
          <CredibilityBadge score={item.credibility_score} size="sm" />
        </View>

        {/* Content */}
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.snippet} numberOfLines={2}>
          {item.snippet}
        </Text>

        {/* Risk Tags */}
        {item.risk_tags.length > 0 && (
          <View style={styles.tagsContainer}>
            {item.risk_tags.slice(0, 3).map((tag, index) => (
              <View
                key={index}
                style={[
                  styles.tag,
                  { borderColor: getRiskTagColor(tag) },
                ]}
              >
                <Text
                  style={[
                    styles.tagText,
                    { color: getRiskTagColor(tag) },
                  ]}
                >
                  {tag.replace(/_/g, ' ')}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Footer */}
        <View style={styles.footer}>
          <View style={styles.platformBadge}>
            <Ionicons
              name={getPlatformIcon(item.source_platform)}
              size={14}
              color={theme.colors.text.muted}
            />
            <Text style={styles.platformText}>{item.source_platform}</Text>
          </View>
          <Ionicons
            name="chevron-forward"
            size={20}
            color={theme.colors.text.muted}
          />
        </View>
      </View>
    </TouchableOpacity>
  );
};

const getPlatformIcon = (platform: string): keyof typeof Ionicons.glyphMap => {
  switch (platform.toLowerCase()) {
    case 'twitter':
    case 'x':
      return 'logo-twitter';
    case 'weibo':
      return 'chatbubbles-outline';
    case 'news':
      return 'newspaper-outline';
    case 'academic':
      return 'school-outline';
    default:
      return 'globe-outline';
  }
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.background.tertiary,
    borderRadius: theme.borderRadius.xl,
    borderWidth: 1,
    borderColor: theme.colors.border.default,
    padding: theme.spacing.lg,
    gap: 10,
    ...theme.shadows.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  source: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.md,
    fontWeight: '600',
  },
  title: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.xl,
    fontWeight: '700',
    lineHeight: 22,
  },
  snippet: {
    color: theme.colors.text.tertiary,
    fontSize: theme.fontSize.base,
    lineHeight: 20,
  },
  tagsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 4,
  },
  tag: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.sm,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  tagText: {
    fontSize: theme.fontSize.xs,
    fontWeight: '500',
    textTransform: 'capitalize',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  platformBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  platformText: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
    textTransform: 'capitalize',
  },
});

export default FeedCard;
