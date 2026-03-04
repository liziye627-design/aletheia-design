/**
 * Aletheia Theme - Dark Mode Design System
 * Based on aletheia-ui.pen design specifications
 */

export const colors = {
  // Primary colors
  primary: {
    main: '#2563EB',     // Logo blue
    light: '#3B82F6',
    dark: '#1D4ED8',
    glow: '#2563EB44',   // For shadows
  },

  // Brand colors
  brand: {
    wechat: '#07C160',   // WeChat green
    success: '#059669',  // Emerald
    successDark: '#052E16',
    successLight: '#ECFDF5',
  },

  // Background colors (Dark theme)
  background: {
    primary: '#050505',
    secondary: '#0A0A0A',
    tertiary: '#111827',
    card: '#171717',
    elevated: '#1F2937',
  },

  // Text colors
  text: {
    primary: '#FFFFFF',
    secondary: '#E5E7EB',
    tertiary: '#A3A3A3',
    muted: '#737373',
    placeholder: '#525252',
  },

  // Border colors
  border: {
    default: '#262626',
    light: '#1F2937',
    dark: '#111827',
  },

  // Status colors
  status: {
    true: '#22C55E',
    false: '#EF4444',
    uncertain: '#F59E0B',
    neutral: '#6B7280',
  },

  // Surface colors
  surface: {
    dark: '#0A0A0A',
    medium: '#111827',
    light: '#1F2937',
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const borderRadius = {
  xs: 4,
  sm: 8,
  md: 10,
  lg: 14,
  xl: 20,
  xxl: 24,
  full: 28,
  round: 99,
} as const;

export const fontSize = {
  xs: 10,
  sm: 11,
  md: 12,
  base: 13,
  lg: 14,
  xl: 16,
  xxl: 18,
  xxxl: 22,
  title: 24,
  hero: 28,
} as const;

export const fontWeight = {
  normal: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
  extrabold: '800',
  black: '900',
} as const;

export const shadows = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 4,
  },
  lg: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 8,
  },
  glow: (color: string) => ({
    shadowColor: color,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 32,
    elevation: 16,
  }),
} as const;

export const theme = {
  colors,
  spacing,
  borderRadius,
  fontSize,
  fontWeight,
  shadows,
} as const;

export type Theme = typeof theme;
export default theme;
