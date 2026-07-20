export const queryKeys = {
  user: ['user'] as const,
  organizations: ['organizations'] as const,
  organization: (id: string) => ['organizations', id] as const,
  workspace: (id: string) => ['workspaces', id] as const,
  workspaces: (organizationId: string) => ['workspaces', { organizationId }] as const,
  missions: (workspaceId: string) => ['missions', workspaceId] as const,
  mission: (missionId: string) => ['mission', missionId] as const,
  missionReceipt: (missionId: string) => ['mission', missionId, 'receipt'] as const,
  missionEvidence: (missionId: string) => ['mission', missionId, 'evidence'] as const,
  conversation: (conversationId: string) => ['conversation', conversationId] as const,
  repository: (repositoryId: string) => ['repositories', repositoryId] as const,
  fileTree: (workspaceId: string) => ['workspaces', workspaceId, 'file-tree'] as const,
  billing: (organizationId: string) => ['billing', organizationId] as const,
  adminReleaseReadiness: ['admin', 'release-readiness'] as const,
  serviceHealth: ['service-health'] as const,
};

