/**
 * API Configuration
 * Connects to Aletheia Backend
 */

// Backend API base URL - adjust based on environment
const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ||
  (__DEV__ ? 'http://localhost:8000' : 'https://api.aletheia.app');

export const API_CONFIG = {
  baseURL: API_BASE_URL,
  apiVersion: '/api/v1',
  timeout: 30000,  // 30 seconds
  
  // Endpoints
  endpoints: {
    // Auth
    auth: {
      login: '/auth/login',
      register: '/auth/register',
      refresh: '/auth/refresh',
      logout: '/auth/logout',
    },
    
    // Intelligence
    intel: {
      analyze: '/intel/analyze',
      batch: '/intel/batch',
      search: '/intel/search',
      trending: '/intel/trending',
      detail: (id: string) => `/intel/${id}`,
    },
    
    // Enhanced Intel
    intelEnhanced: {
      base: '/intel/enhanced',
    },
    
    // Vision
    vision: {
      base: '/vision',
    },
    
    // Reports
    reports: {
      list: '/reports',
      detail: (id: string) => `/reports/${id}`,
      generate: '/reports/generate',
    },
    
    // Feeds
    feeds: {
      list: '/feeds',
      filter: '/feeds/filter',
    },
    
    // Multi-platform
    multiplatform: {
      base: '/multiplatform',
    },
    
    // Health
    health: '/health',
  },
} as const;

export default API_CONFIG;
