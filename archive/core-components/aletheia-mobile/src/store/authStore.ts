/**
 * Auth Store - Zustand store for authentication state
 */

import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { authService } from '../services/auth';
import type { User } from '../types';

const TOKEN_KEY = 'aletheia_auth_token';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  login: (email: string, password: string) => Promise<void>;
  loginWithWechat: () => Promise<void>;
  register: (email: string, password: string, username: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authService.login({ email, password });
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Login failed';
      set({
        isLoading: false,
        error: message,
      });
      throw new Error(message);
    }
  },

  loginWithWechat: async () => {
    set({ isLoading: true, error: null });
    try {
      // TODO: Implement WeChat OAuth
      // 1. Open WeChat auth page
      // 2. Get auth code
      // 3. Send to backend
      // 4. Receive tokens
      
      // For now, mock success
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      set({
        user: {
          id: 'wechat_user_1',
          email: 'wechat@example.com',
          username: 'WeChat User',
          created_at: new Date().toISOString(),
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error: any) {
      const message = error.message || 'WeChat login failed';
      set({
        isLoading: false,
        error: message,
      });
      throw new Error(message);
    }
  },

  register: async (email: string, password: string, username: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authService.register({ email, password, username });
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Registration failed';
      set({
        isLoading: false,
        error: message,
      });
      throw new Error(message);
    }
  },

  logout: async () => {
    set({ isLoading: true });
    try {
      await authService.logout();
    } catch (error) {
      console.warn('Logout error:', error);
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token) {
        // TODO: Validate token with backend
        // For now, assume valid if token exists
        set({
          isAuthenticated: true,
          isLoading: false,
        });
      } else {
        set({
          isAuthenticated: false,
          isLoading: false,
        });
      }
    } catch (error) {
      console.warn('Auth check error:', error);
      set({
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));

export default useAuthStore;
