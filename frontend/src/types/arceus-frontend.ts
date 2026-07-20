export type ArceusClientSurface = 'web' | 'desktop' | 'admin' | 'auth' | 'docs';

export type ArceusRouteBoundary =
  | 'marketing'
  | 'auth'
  | 'workspace'
  | 'settings'
  | 'admin'
  | 'docs'
  | 'unknown';

export type MissionStatus =
  | 'draft'
  | 'planning'
  | 'awaiting_approval'
  | 'running'
  | 'paused'
  | 'blocked'
  | 'failed'
  | 'completed'
  | 'cancelled';

export type AgentStatus = 'queued' | 'thinking' | 'running' | 'waiting' | 'blocked' | 'failed' | 'completed';

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export type MessageContentType =
  | 'text'
  | 'markdown'
  | 'code'
  | 'image'
  | 'file'
  | 'tool_call'
  | 'tool_result'
  | 'diff'
  | 'approval'
  | 'citation'
  | 'mission_reference';

export type GitFileStatus = 'added' | 'modified' | 'deleted' | 'renamed' | 'untracked' | 'conflicted' | 'clean';

export interface WorkspaceContext {
  organizationId: string;
  workspaceId: string;
  repositoryId?: string;
  activeMissionId?: string;
  activeConversationId?: string;
  desktopCapabilities?: DesktopCapabilities;
}

export interface DesktopCapabilities {
  fileSystem: boolean;
  terminal: boolean;
  git: boolean;
  localModels: boolean;
  systemNotifications: boolean;
  autoUpdate: boolean;
}

export interface ConversationMessage {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: Array<{
    type: MessageContentType;
    value: unknown;
    metadata?: Record<string, unknown>;
  }>;
  status: 'queued' | 'streaming' | 'completed' | 'failed' | 'cancelled';
  model?: string;
  createdAt: string;
  parentMessageId?: string;
}

export interface MissionSummary {
  id: string;
  objective: string;
  status: MissionStatus;
  ownerId?: string;
  costUsd?: number;
  durationMs?: number;
  progress?: number;
}

export interface AgentActivity {
  id: string;
  name: string;
  role: string;
  model?: string;
  currentTask?: string;
  status: AgentStatus;
  elapsedMs?: number;
  tokenUsage?: number;
  latestAction?: string;
  dependencies?: string[];
  errors?: string[];
}

export interface ApprovalCardModel {
  id: string;
  action: string;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  reason: string;
  affectedResources: string[];
  proposedChanges: string[];
  rollbackPlan?: string;
  evidenceIds: string[];
}

export interface FileTreeNode {
  id: string;
  path: string;
  name: string;
  type: 'file' | 'directory';
  gitStatus?: GitFileStatus;
  children?: FileTreeNode[];
  expanded?: boolean;
  dirty?: boolean;
  ignored?: boolean;
}

export interface Command {
  id: string;
  title: string;
  category: string;
  shortcut?: string;
  enabled: boolean;
  execute(): Promise<void> | void;
}

