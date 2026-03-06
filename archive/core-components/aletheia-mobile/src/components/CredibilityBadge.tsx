/**
 * CredibilityBadge Component - Shows credibility score with color coding
 */

import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { theme } from '../utils/theme';

interface CredibilityBadgeProps {
  score: number; // 0.0 - 1.0
  size?: 'sm' | 'md' | 'lg';
  showPercentage?: boolean;
  style?: ViewStyle;
}

export const CredibilityBadge: React.FC<CredibilityBadgeProps> = ({
  score,
  size = 'md',
  showPercentage = true,
  style,
}) => {
  const getColor = () => {
    if (score >= 0.8) return theme.colors.status.true;
    if (score >= 0.5) return theme.colors.status.uncertain;
    return theme.colors.status.false;
  };

  const getBackgroundColor = () => {
    if (score >= 0.8) return theme.colors.brand.successLight;
    if (score >= 0.5) return '#FEF3C7'; // Amber light
    return '#FEE2E2'; // Red light
  };

  const getLabel = () => {
    if (score >= 0.8) return 'True';
    if (score >= 0.5) return 'Uncertain';
    return 'False';
  };

  const getSizeStyle = () => {
    switch (size) {
      case 'sm':
        return {
          paddingHorizontal: 8,
          paddingVertical: 2,
          fontSize: theme.fontSize.xs,
        };
      case 'lg':
        return {
          paddingHorizontal: 14,
          paddingVertical: 6,
          fontSize: theme.fontSize.base,
        };
      default:
        return {
          paddingHorizontal: 10,
          paddingVertical: 4,
          fontSize: theme.fontSize.sm,
        };
    }
  };

  const sizeStyle = getSizeStyle();
  const color = getColor();
  const backgroundColor = getBackgroundColor();

  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor,
          paddingHorizontal: sizeStyle.paddingHorizontal,
          paddingVertical: sizeStyle.paddingVertical,
        },
        style,
      ]}
    >
      <Text
        style={[
          styles.text,
          { color, fontSize: sizeStyle.fontSize },
        ]}
      >
        {showPercentage ? `${Math.round(score * 100)}% ` : ''}
        {getLabel()}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    borderRadius: theme.borderRadius.round,
    alignSelf: 'flex-start',
  },
  text: {
    fontWeight: '700',
  },
});

export default CredibilityBadge;
