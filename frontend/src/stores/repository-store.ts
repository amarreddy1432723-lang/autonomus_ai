'use client';

import { create } from 'zustand';
import { apiRequest } from '../utils/api';

export type RepositoryService = {
  name: string;
};

export type RepositoryStatus = 'idle' | 'analyzing' | 'ready' | 'failed';

export interface RepositoryState {
  repositoryId?: string;
  rootPath?: string;
  name?: string;
  status: RepositoryStatus;
  error?: string;
  cached?: boolean;
  scannedFiles: number;
  skippedFiles: number;
  languages: string[];
  frameworks: string[];
  packageManagers: string[];
  services: RepositoryService[];
  entryPoints: string[];
  testCommands: string[];
  databaseUsage: string[];
  authentication: string[];
  architectureStyle?: string;
  summary?: string;
  analyzedAt?: string;
  analyzeRepository: (rootPath: string, options?: { force?: boolean }) => Promise<void>;
  resetRepository: () => void;
}

const initialState = {
  repositoryId: undefined,
  rootPath: undefined,
  name: undefined,
  status: 'idle' as RepositoryStatus,
  error: undefined,
  cached: false,
  scannedFiles: 0,
  skippedFiles: 0,
  languages: [],
  frameworks: [],
  packageManagers: [],
  services: [],
  entryPoints: [],
  testCommands: [],
  databaseUsage: [],
  authentication: [],
  architectureStyle: undefined,
  summary: undefined,
  analyzedAt: undefined,
};

function nameFromRoot(rootPath: string) {
  return rootPath.split(/[\\/]/).filter(Boolean).pop() || 'Repository';
}

export const useRepositoryStore = create<RepositoryState>((set) => ({
  ...initialState,
  analyzeRepository: async (rootPath, options = {}) => {
    const normalizedRoot = rootPath.trim();
    if (!normalizedRoot) {
      set({ ...initialState });
      return;
    }

    set({
      status: 'analyzing',
      error: undefined,
      rootPath: normalizedRoot,
      name: nameFromRoot(normalizedRoot),
    });

    try {
      const result = await apiRequest('/api/v1/repositories/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: `local:${normalizedRoot}`,
          root_path: normalizedRoot,
          force: Boolean(options.force),
        }),
      });

      set({
        repositoryId: result.repository_id,
        rootPath: normalizedRoot,
        name: nameFromRoot(normalizedRoot),
        status: 'ready',
        error: undefined,
        cached: Boolean(result.cached),
        scannedFiles: result.scanned_files || 0,
        skippedFiles: result.skipped_files || 0,
        languages: result.languages || [],
        frameworks: result.frameworks || [],
        packageManagers: result.package_managers || [],
        services: (result.services || []).map((name: string) => ({ name })),
        entryPoints: result.entry_points || [],
        testCommands: result.test_commands || [],
        databaseUsage: result.database_usage || [],
        authentication: result.authentication || [],
        architectureStyle: result.architecture_style,
        summary: result.summary,
        analyzedAt: result.analyzed_at,
      });
    } catch (error) {
      set({
        status: 'failed',
        error: error instanceof Error ? error.message : 'Repository analysis failed.',
      });
    }
  },
  resetRepository: () => set({ ...initialState }),
}));
