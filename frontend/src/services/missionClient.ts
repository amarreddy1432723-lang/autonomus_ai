import { baseApiClient } from './baseApiClient';
import type { ApprovalCardModel, AgentActivity, MissionSummary } from '@/types/arceus-frontend';

export interface CreateMissionInput {
  workspaceId: string;
  objective: string;
  constraints?: string[];
  expectedOutputs?: string[];
}

export interface ApprovalInput {
  decision: 'approve' | 'reject' | 'request_changes';
  comment?: string;
}

export interface MissionClient {
  create(input: CreateMissionInput): Promise<MissionSummary>;
  get(id: string): Promise<MissionSummary>;
  run(id: string): Promise<MissionSummary>;
  pause(id: string): Promise<MissionSummary>;
  cancel(id: string): Promise<MissionSummary>;
  agents(id: string): Promise<AgentActivity[]>;
  approvals(id: string): Promise<ApprovalCardModel[]>;
  approveStep(missionId: string, stepId: string, input: ApprovalInput): Promise<void>;
}

export const missionClient: MissionClient = {
  create(input) {
    return baseApiClient.request<MissionSummary>('/api/v1/runtime/missions', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },
  get(id) {
    return baseApiClient.request<MissionSummary>(`/api/v1/runtime/missions/${encodeURIComponent(id)}`);
  },
  run(id) {
    return baseApiClient.request<MissionSummary>(`/api/v1/runtime/missions/${encodeURIComponent(id)}/run`, { method: 'POST' });
  },
  pause(id) {
    return baseApiClient.request<MissionSummary>(`/api/v1/runtime/missions/${encodeURIComponent(id)}/pause`, { method: 'POST' });
  },
  cancel(id) {
    return baseApiClient.request<MissionSummary>(`/api/v1/runtime/missions/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
  },
  agents(id) {
    return baseApiClient.request<AgentActivity[]>(`/api/v1/runtime/missions/${encodeURIComponent(id)}/agents`);
  },
  approvals(id) {
    return baseApiClient.request<ApprovalCardModel[]>(`/api/v1/runtime/missions/${encodeURIComponent(id)}/approvals`);
  },
  approveStep(missionId, stepId, input) {
    return baseApiClient.request<void>(
      `/api/v1/runtime/missions/${encodeURIComponent(missionId)}/steps/${encodeURIComponent(stepId)}/approval`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      }
    );
  },
};

