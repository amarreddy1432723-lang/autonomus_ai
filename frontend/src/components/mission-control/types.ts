export type MissionRuntimeStatus =
  | 'awaiting_approval'
  | 'queued'
  | 'running'
  | 'verifying'
  | 'attention_required'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string;

export type MissionControlMission = {
  title?: string;
  repositoryName?: string;
  status?: MissionRuntimeStatus;
  durationSeconds?: number | null;
  progress?: number;
};

export type MissionControlWorker = {
  workerId?: string;
  role: string;
  status: string;
  currentTaskKey?: string | null;
  currentTaskTitle?: string | null;
  assignmentStatus?: string | null;
  heartbeatAgeSeconds?: number | null;
  confidence?: number | null;
};

export type MissionControlTask = {
  taskId: string;
  taskKey: string;
  title: string;
  status: string;
  blockedReason?: string | null;
  assignmentStatus?: string | null;
};

export type MissionControlEdge = {
  fromTaskKey?: string | null;
  toTaskKey?: string | null;
  dependencyType?: string;
};

export type MissionControlEvent = {
  eventId?: string;
  eventType?: string;
  actorType?: string;
  actorId?: string | null;
  occurredAt?: string | null;
  payload?: Record<string, unknown>;
};

export type MissionControlLock = {
  reservationId: string;
  pathPattern: string;
  reservationMode: string;
  status: string;
  taskKey?: string | null;
  acquiredAt?: string | null;
};

export type MissionControlRecovery = {
  assignmentId: string;
  taskKey?: string | null;
  status?: string;
  localStage?: string;
  repositoryState?: string;
  recommendedAction?: string;
};

export type MissionControlEvidence = {
  id: string;
  summary: string;
  status: string;
  evidenceType?: string;
  createdAt?: string | null;
};

export type MissionControlMetricsData = {
  taskCount?: number;
  completedTasks?: number;
  activeAssignments?: number;
  readyTasks?: number;
  runningTasks?: number;
  blockedTasks?: number;
  activeReservations?: number;
  recoveryReports?: number;
  manualReviewRequired?: number;
  averageQueueSeconds?: number | null;
  missionDurationSeconds?: number | null;
  evidenceCount?: number;
};
