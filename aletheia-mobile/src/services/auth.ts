/**
 * Auth Service - Authentication API calls
 */

import apiClient from './api';
import { API_CONFIG } from './config';
import type { AuthResponse, LoginRequest, RegisterRequest, User } from '../types';

export const authService = {
  /**
   * Login with email and password
   */
  async login(credentials: LoginRequest): Promise<AuthResponse> {
    const response = await apiClient.post<AuthResponse>(
      API_CONFIG.endpoints.auth.login,
      credentials
    );
    
    // Store tokens
    await apiClient.setTokens(response.access_token, response.refresh_token);
    
    return response;
  },

  /**
   * Register new user
   */
  async register(data: RegisterRequest): Promise<AuthResponse> {
    const response = await apiClient.post<AuthResponse>(
      API_CONFIG.endpoints.auth.register,
      data
    );
    
    // Store tokens
    await apiClient.setTokens(response.access_token, response.refresh_token);
    
    return response;
  },

  /**
   * Logout - clear tokens
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post(API_CONFIG.endpoints.auth.logout);
    } catch (error) {
      // Ignore logout API errors
      console.warn('Logout API error:', error);
    } finally {
      await apiClient.clearTokens();
    }
  },

  /**
   * Check if user is authenticated
   */
  async checkAuth(): Promise<boolean> {
    const token = await apiClient.getAccessToken();
    return !!token;
  },

  /**
   * Get current user profile
   */
  async getProfile(): Promise<User> {
    // TODO: Implement when backend has profile endpoint
    throw new Error('Not implemented');
  },
};

export default authService;
