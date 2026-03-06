import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { AppState } from '../types';

/**
 * Aletheia 全局状态管理
 * 使用 Zustand 替代分散的 useState
 */
export const useAppStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        // 初始状态
        analysisResult: null,
        isAnalyzing: false,
        searchResult: null,
        isSearching: false,
        historyItems: [],
        activeTab: 'verify',

        // Actions
        setAnalysisResult: (result) => set({ analysisResult: result }),
        setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
        setSearchResult: (result) => set({ searchResult: result }),
        setIsSearching: (isSearching) => set({ isSearching }),
        setActiveTab: (tab) => set({ activeTab: tab }),
        addHistoryItem: (item) =>
          set((state) => ({
            historyItems: [item, ...state.historyItems].slice(0, 50), // 最多保留50条
          })),
      }),
      {
        name: 'aletheia-storage',
        partialize: (state) => ({ historyItems: state.historyItems }), // 只持久化历史记录
      }
    ),
    { name: 'AletheiaStore' }
  )
);

// ===== 便捷 hooks =====

export const useAnalysis = () => {
  const { analysisResult, isAnalyzing, setAnalysisResult, setIsAnalyzing } = useAppStore();
  return { analysisResult, isAnalyzing, setAnalysisResult, setIsAnalyzing };
};

export const useSearch = () => {
  const { searchResult, isSearching, setSearchResult, setIsSearching } = useAppStore();
  return { searchResult, isSearching, setSearchResult, setIsSearching };
};

export const useHistory = () => {
  const { historyItems, addHistoryItem } = useAppStore();
  return { historyItems, addHistoryItem };
};

export const useNavigation = () => {
  const { activeTab, setActiveTab } = useAppStore();
  return { activeTab, setActiveTab };
};
