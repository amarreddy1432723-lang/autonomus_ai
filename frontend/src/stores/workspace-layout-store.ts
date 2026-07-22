'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type PrimarySidebarView = 'explorer' | 'search' | 'source-control' | 'missions' | 'extensions';
export type BottomPanelView = 'terminal' | 'problems' | 'output' | 'tests' | 'logs';

export const WORKSPACE_LAYOUT_STORAGE_KEY = 'arceus.workspace.layout.v1';

export const WORKSPACE_LAYOUT_LIMITS = {
  sidebar: { min: 180, max: 420, default: 240 },
  aiPanel: { min: 280, max: 560, default: 360 },
  bottomPanel: { min: 120, max: 500, default: 220 },
} as const;

type WorkspaceLayoutState = {
  activeSidebarView: PrimarySidebarView;
  activeBottomPanelView: BottomPanelView;
  sidebarVisible: boolean;
  aiPanelVisible: boolean;
  bottomPanelVisible: boolean;
  sidebarWidth: number;
  aiPanelWidth: number;
  bottomPanelHeight: number;
  setActiveSidebarView: (view: PrimarySidebarView) => void;
  setActiveBottomPanelView: (view: BottomPanelView) => void;
  setSidebarVisible: (visible: boolean) => void;
  setAIPanelVisible: (visible: boolean) => void;
  setBottomPanelVisible: (visible: boolean) => void;
  toggleSidebar: (view?: PrimarySidebarView) => void;
  toggleAIPanel: () => void;
  toggleBottomPanel: (view?: BottomPanelView) => void;
  setSidebarWidth: (width: number) => void;
  setAIPanelWidth: (width: number) => void;
  setBottomPanelHeight: (height: number) => void;
  resetLayout: () => void;
};

const defaultLayout = {
  activeSidebarView: 'explorer' as PrimarySidebarView,
  activeBottomPanelView: 'terminal' as BottomPanelView,
  sidebarVisible: true,
  aiPanelVisible: true,
  bottomPanelVisible: true,
  sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebar.default,
  aiPanelWidth: WORKSPACE_LAYOUT_LIMITS.aiPanel.default,
  bottomPanelHeight: WORKSPACE_LAYOUT_LIMITS.bottomPanel.default,
};

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
}

export const useWorkspaceLayoutStore = create<WorkspaceLayoutState>()(
  persist(
    (set) => ({
      ...defaultLayout,
      setActiveSidebarView: (view) => set({ activeSidebarView: view, sidebarVisible: true }),
      setActiveBottomPanelView: (view) => set({ activeBottomPanelView: view, bottomPanelVisible: true }),
      setSidebarVisible: (visible) => set({ sidebarVisible: visible }),
      setAIPanelVisible: (visible) => set({ aiPanelVisible: visible }),
      setBottomPanelVisible: (visible) => set({ bottomPanelVisible: visible }),
      toggleSidebar: (view) =>
        set((state) => {
          const nextView = view ?? state.activeSidebarView;
          const sameOpenView = state.sidebarVisible && nextView === state.activeSidebarView;
          return {
            activeSidebarView: nextView,
            sidebarVisible: !sameOpenView,
          };
        }),
      toggleAIPanel: () => set((state) => ({ aiPanelVisible: !state.aiPanelVisible })),
      toggleBottomPanel: (view) =>
        set((state) => {
          const nextView = view ?? state.activeBottomPanelView;
          const sameOpenView = state.bottomPanelVisible && nextView === state.activeBottomPanelView;
          return {
            activeBottomPanelView: nextView,
            bottomPanelVisible: !sameOpenView,
          };
        }),
      setSidebarWidth: (width) =>
        set({ sidebarWidth: clamp(width, WORKSPACE_LAYOUT_LIMITS.sidebar.min, WORKSPACE_LAYOUT_LIMITS.sidebar.max) }),
      setAIPanelWidth: (width) =>
        set({ aiPanelWidth: clamp(width, WORKSPACE_LAYOUT_LIMITS.aiPanel.min, WORKSPACE_LAYOUT_LIMITS.aiPanel.max) }),
      setBottomPanelHeight: (height) =>
        set({ bottomPanelHeight: clamp(height, WORKSPACE_LAYOUT_LIMITS.bottomPanel.min, WORKSPACE_LAYOUT_LIMITS.bottomPanel.max) }),
      resetLayout: () => set(defaultLayout),
    }),
    {
      name: WORKSPACE_LAYOUT_STORAGE_KEY,
      partialize: (state) => ({
        activeSidebarView: state.activeSidebarView,
        activeBottomPanelView: state.activeBottomPanelView,
        sidebarVisible: state.sidebarVisible,
        aiPanelVisible: state.aiPanelVisible,
        bottomPanelVisible: state.bottomPanelVisible,
        sidebarWidth: state.sidebarWidth,
        aiPanelWidth: state.aiPanelWidth,
        bottomPanelHeight: state.bottomPanelHeight,
      }),
    },
  ),
);
