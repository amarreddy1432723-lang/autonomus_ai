import { create } from 'zustand';

import { apiRequest } from '../utils/api';
import type { RepositoryState } from './repository-store';

type MissionTask = {
  task_key: string;
  title: string;
  task_type: string;
  dependencies: string[];
  risk_level: string;
  estimated_seconds: number;
};

type MissionAgent = {
  task_id: string;
  role: string;
  model: string;
  estimated_tokens: number;
  reason: string;
};

type MissionReport = {
  mission: string;
  status: string;
  estimated_duration_minutes: number;
  files_likely_modified: number;
  tests_planned: string[];
  warnings: string[];
  rollback_available: boolean;
  confidence: number;
};

export type CognitiveMissionPreview = {
  mission_id: string;
  state: 'AWAITING_APPROVAL' | 'CLARIFICATION_REQUIRED';
  goal: string;
  understanding: {
    intent: string;
    domain: string;
    priority: string;
    repository_scope: string[];
    requires_database: boolean;
    requires_ui: boolean;
    requires_tests: boolean;
    risk_level: string;
    unknowns: string[];
  };
  tasks: MissionTask[];
  dependency_graph: {
    valid: boolean;
    topological_order: string[];
    critical_path: string[];
    edge_count: number;
  };
  agents: MissionAgent[];
  recovery_strategy: string[];
  report: MissionReport;
};

type CognitiveMissionStore = {
  status: 'idle' | 'compiling' | 'ready' | 'failed';
  error: string;
  preview: CognitiveMissionPreview | null;
  compileMission: (goal: string, repository: RepositoryState) => Promise<CognitiveMissionPreview | null>;
  clearMission: () => void;
};

function repositoryPayload(repository: RepositoryState) {
  if (repository.status !== 'ready') return null;
  return {
    repository_id: repository.repositoryId,
    root_path: repository.rootPath,
    summary: repository.summary,
    languages: repository.languages,
    frameworks: repository.frameworks,
    package_managers: repository.packageManagers,
    entry_points: repository.entryPoints,
    services: repository.services,
    test_commands: repository.testCommands,
    database_usage: repository.databaseUsage,
    authentication: repository.authentication,
    architecture_style: repository.architectureStyle,
  };
}

export const useCognitiveMissionStore = create<CognitiveMissionStore>((set) => ({
  status: 'idle',
  error: '',
  preview: null,

  compileMission: async (goal, repository) => {
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) return null;
    set({ status: 'compiling', error: '' });
    try {
      const result = await apiRequest('/api/v1/missions/compile-cognitive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: trimmedGoal,
          workspace_id: repository.rootPath ? `local:${repository.rootPath}` : 'local-workspace',
          repository: repositoryPayload(repository),
          approval_mode: 'preview',
        }),
      });
      set({ status: 'ready', preview: result, error: '' });
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Mission compile failed.';
      set({ status: 'failed', error: message });
      return null;
    }
  },

  clearMission: () => set({ status: 'idle', error: '', preview: null }),
}));
