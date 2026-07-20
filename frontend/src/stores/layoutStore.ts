import { create } from 'zustand';

type PanelId = 'explorer' | 'changes' | 'jobs' | 'preview' | 'git' | 'tasks' | 'terminal' | 'problems';

interface LayoutStore {
  sidebarCollapsed: boolean;
  commandPaletteOpen: boolean;
  bottomPanel: PanelId | null;
  rightPanel: PanelId | null;
  panelSizes: Record<string, number>;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setBottomPanel: (panel: PanelId | null) => void;
  setRightPanel: (panel: PanelId | null) => void;
  setPanelSize: (panel: string, size: number) => void;
}

export const useLayoutStore = create<LayoutStore>((set) => ({
  sidebarCollapsed: false,
  commandPaletteOpen: false,
  bottomPanel: 'terminal',
  rightPanel: null,
  panelSizes: {
    sidebar: 280,
    rightPanel: 360,
    bottomPanel: 280,
  },
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
  setBottomPanel: (panel) => set({ bottomPanel: panel }),
  setRightPanel: (panel) => set({ rightPanel: panel }),
  setPanelSize: (panel, size) => set((state) => ({ panelSizes: { ...state.panelSizes, [panel]: size } })),
}));

