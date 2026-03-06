/**
 * Feeds Store - Zustand store for feeds state
 */

import { create } from 'zustand';
import { feedsService } from '../services/feeds';
import type { FeedItem } from '../types';

interface FeedsState {
  items: FeedItem[];
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  page: number;
  hasMore: boolean;
  
  // Actions
  fetchFeeds: (refresh?: boolean) => Promise<void>;
  loadMore: () => Promise<void>;
  clearError: () => void;
}

export const useFeedsStore = create<FeedsState>((set, get) => ({
  items: [],
  isLoading: false,
  isRefreshing: false,
  error: null,
  page: 1,
  hasMore: true,

  fetchFeeds: async (refresh = false) => {
    const state = get();
    
    if (state.isLoading) return;
    
    set({ 
      isLoading: !refresh,
      isRefreshing: refresh,
      error: null 
    });
    
    try {
      // Use mock data for development
      // TODO: Replace with actual API call when backend is ready
      const mockItems = feedsService.getMockFeeds();
      
      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 500));
      
      set({
        items: mockItems,
        page: 1,
        hasMore: true,
        isLoading: false,
        isRefreshing: false,
      });
      
      /* 
      // Actual API call (uncomment when backend is ready)
      const response = await feedsService.getFeeds({ page: 1 });
      set({
        items: response.items,
        page: 1,
        hasMore: response.has_more,
        isLoading: false,
        isRefreshing: false,
      });
      */
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to load feeds';
      set({
        error: message,
        isLoading: false,
        isRefreshing: false,
      });
    }
  },

  loadMore: async () => {
    const state = get();
    
    if (state.isLoading || !state.hasMore) return;
    
    set({ isLoading: true, error: null });
    
    try {
      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // For mock data, just indicate no more items
      set({
        hasMore: false,
        isLoading: false,
      });
      
      /*
      // Actual API call (uncomment when backend is ready)
      const response = await feedsService.getFeeds({ page: nextPage });
      set({
        items: [...state.items, ...response.items],
        page: nextPage,
        hasMore: response.has_more,
        isLoading: false,
      });
      */
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to load more feeds';
      set({
        error: message,
        isLoading: false,
      });
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));

export default useFeedsStore;
