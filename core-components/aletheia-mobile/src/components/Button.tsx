/**
 * Button Component - Primary button with multiple variants
 */

import React from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { theme } from '../utils/theme';

type ButtonVariant = 'primary' | 'secondary' | 'wechat' | 'outline' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  icon?: React.ReactNode;
  style?: ViewStyle;
  textStyle?: TextStyle;
}

export const Button: React.FC<ButtonProps> = ({
  title,
  onPress,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  icon,
  style,
  textStyle,
}) => {
  const getVariantStyle = (): ViewStyle => {
    switch (variant) {
      case 'primary':
        return {
          backgroundColor: theme.colors.brand.success,
        };
      case 'wechat':
        return {
          backgroundColor: theme.colors.brand.wechat,
        };
      case 'secondary':
        return {
          backgroundColor: theme.colors.background.card,
          borderWidth: 1,
          borderColor: theme.colors.border.default,
        };
      case 'outline':
        return {
          backgroundColor: 'transparent',
          borderWidth: 1,
          borderColor: theme.colors.border.default,
        };
      case 'ghost':
        return {
          backgroundColor: 'transparent',
        };
      default:
        return {};
    }
  };

  const getTextStyle = (): TextStyle => {
    switch (variant) {
      case 'primary':
        return {
          color: theme.colors.brand.successDark,
        };
      case 'wechat':
        return {
          color: '#FFFFFF',
        };
      case 'secondary':
      case 'outline':
        return {
          color: theme.colors.text.secondary,
        };
      case 'ghost':
        return {
          color: theme.colors.text.tertiary,
        };
      default:
        return {};
    }
  };

  const getSizeStyle = (): { button: ViewStyle; text: TextStyle } => {
    switch (size) {
      case 'sm':
        return {
          button: { height: 36, paddingHorizontal: 16, borderRadius: theme.borderRadius.md },
          text: { fontSize: theme.fontSize.base },
        };
      case 'lg':
        return {
          button: { height: 56, paddingHorizontal: 24, borderRadius: theme.borderRadius.full },
          text: { fontSize: theme.fontSize.xl },
        };
      default:
        return {
          button: { height: 44, paddingHorizontal: 20, borderRadius: theme.borderRadius.lg },
          text: { fontSize: theme.fontSize.lg },
        };
    }
  };

  const sizeStyle = getSizeStyle();

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled || loading}
      style={[
        styles.button,
        getVariantStyle(),
        sizeStyle.button,
        disabled && styles.disabled,
        style,
      ]}
      activeOpacity={0.8}
    >
      {loading ? (
        <ActivityIndicator
          color={variant === 'primary' ? theme.colors.brand.successDark : theme.colors.text.secondary}
          size="small"
        />
      ) : (
        <>
          {icon}
          <Text
            style={[
              styles.text,
              getTextStyle(),
              sizeStyle.text,
              icon ? styles.textWithIcon : undefined,
              textStyle,
            ]}
          >
            {title}
          </Text>
        </>
      )}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  text: {
    fontWeight: '700',
  },
  textWithIcon: {
    marginLeft: 8,
  },
  disabled: {
    opacity: 0.5,
  },
});

export default Button;
