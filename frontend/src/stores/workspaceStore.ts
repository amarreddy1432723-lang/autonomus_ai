import { create } from 'zustand';
import type { DesktopCapabilities, WorkspaceContext } from '@/types/arceus-frontend';

interface WorkspaceStore {
  context: WorkspaceContext | null;
  capabilities: DesktopCapabilities;
  dirtyPaths: string[];
  activeFilePath: string | null;
  setContext: (context: WorkspaceContext | null) => void;
  setCapabilities: (capabilities: Partial<DesktopCapabilities>) => void;
  setActiveFilePath: (path: string | null) => void;
  markDirty: (path: string) => void;
  markClean: (path: string) => void;
  resetDirty: () => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  context: null,
  capabilities: {
    fileSystem: false,
    terminal: false,
    git: false,
    localModels: false,
    systemNotifications: false,
    autoUpdate: false,
  },
  dirtyPaths: [],
  activeFilePath: null,
  setContext: (context) => set({ context }),
  setCapabilities: (capabilities) =>
    set((state) => ({ capabilities: { ...state.capabilities, ...capabilities } })),
  setActiveFilePath: (path) => set({ activeFilePath: path }),
  markDirty: (path) =>
    set((state) => ({ dirtyPaths: state.dirtyPaths.includes(path) ? state.dirtyPaths : [...state.dirtyPaths, path] })),
  markClean: (path) => set((state) => ({ dirtyPaths: state.dirtyPaths.filter((item) => item !== path) })),
  resetDirty: () => set({ dirtyPaths: [] }),
}));

