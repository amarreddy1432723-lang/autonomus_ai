import { create } from 'zustand';

import { apiRequest } from '../utils/api';
import type { RepositoryState } from './repository-store';

export type PersistedMissionTask = {
  id: string;
  task_key: string;
  title: string;
  task_type: string;
  status: string;
  agent_role?: string | null;
  model_hint?: string | null;
  dependencies: string[];
};

export type PersistedMissionEvent = {
  id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type PersistedMission = {
  mission_id: string;
  status: string;
  display_status: string;
  version: number;
  goal: string;
  task_count: number;
  dependency_count: number;
  agents: string[];
  confidence: number;
  warnings: string[];
  approval_required: boolean;
  compiled_plan: {
    understanding?: {
      intent?: string;
      domain?: string;
      risk_level?: string;
    };
    tasks?: Array<{ task_key: string; title: string }>;
    report?: { warnings?: string[]; confidence?: number };
  };
  tasks: PersistedMissionTask[];
  events: PersistedMissionEvent[];
};

type MissionStore = {
  status: 'idle' | 'creating' | 'awaiting_approval' | 'queuing' | 'queued' | 'rejected' | 'failed';
  error: string;
  mission: PersistedMission | null;
  createMission: (goal: string, repository: RepositoryState) => Promise<PersistedMission | null>;
  approveMission: () => Promise<PersistedMission | null>;
  rejectMission: (reason?: string) => Promise<PersistedMission | null>;
  loadMission: (missionId: string) => Promise<PersistedMission | null>;
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

function nextStatus(mission: PersistedMission): MissionStore['status'] {
  if (mission.display_status === 'queued') return 'queued';
  if (mission.display_status === 'awaiting_approval') return 'awaiting_approval';
  if (mission.status === 'cancelled') return 'rejected';
  return 'idle';
}

export const useMissionStore = create<MissionStore>((set, get) => ({
  status: 'idle',
  error: '',
  mission: null,

  createMission: async (goal, repository) => {
    const trimmedGoal = goal.trim();
    const repo = repositoryPayload(repository);
    if (!trimmedGoal || !repo) {
      set({ status: 'failed', error: 'Open and analyze a repository before creating a mission.' });
      return null;
    }
    set({ status: 'creating', error: '' });
    try {
      const result = await apiRequest('/api/v1/missions/persisted', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': `desktop-mission-${crypto.randomUUID()}`,
        },
        body: JSON.stringify({
          goal: trimmedGoal,
          workspace_id: repository.rootPath ? `local:${repository.rootPath}` : 'local-workspace',
          repository: repo,
          constraints: { surface: 'arceus-code-desktop' },
        }),
      });
      set({ status: nextStatus(result), mission: result, error: '' });
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Mission persistence failed.';
      set({ status: 'failed', error: message });
      return null;
    }
  },

  approveMission: async () => {
    const mission = get().mission;
    if (!mission) return null;
    set({ status: 'queuing', error: '' });
    try {
      const result = await apiRequest(`/api/v1/missions/persisted/${mission.mission_id}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': `desktop-approve-${mission.mission_id}-${mission.version}`,
        },
        body: JSON.stringify({
          expected_version: mission.version,
          approval_note: 'Approved from Arceus Code desktop.',
        }),
      });
      set({ status: nextStatus(result), mission: result, error: '' });
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Mission approval failed.';
      set({ status: 'failed', error: message });
      return null;
    }
  },

  rejectMission: async (reason = 'Rejected from Arceus Code desktop.') => {
    const mission = get().mission;
    if (!mission) return null;
    set({ status: 'queuing', error: '' });
    try {
      const result = await apiRequest(`/api/v1/missions/persisted/${mission.mission_id}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': `desktop-reject-${mission.mission_id}-${mission.version}`,
        },
        body: JSON.stringify({
          expected_version: mission.version,
          reason,
        }),
      });
      set({ status: nextStatus(result), mission: result, error: '' });
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Mission rejection failed.';
      set({ status: 'failed', error: message });
      return null;
    }
  },

  loadMission: async (missionId) => {
    set({ error: '' });
    try {
      const result = await apiRequest(`/api/v1/missions/persisted/${missionId}`);
      set({ status: nextStatus(result), mission: result, error: '' });
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Mission load failed.';
      set({ status: 'failed', error: message });
      return null;
    }
  },

  clearMission: () => set({ status: 'idle', error: '', mission: null }),
}));
