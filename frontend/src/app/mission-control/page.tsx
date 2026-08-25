'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Bell,
  Check,
  Cloud,
  RefreshCw,
  Search,
  UserRound,
} from 'lucide-react';
import { ApiError, apiRequest } from '../../utils/api';
import { MissionControlProductView } from '../../components/mission-control/MissionControlProductView';
import { ACTIVE_PROJECT_KEY, OPEN_PROJECTS_KEY, type CodeProject } from '../workspace/workspacePageUtils';
import styles from './MissionControl.module.css';

type ApiState = 'loading' | 'live' | 'offline';

type RuntimeMetrics = {
  worker_utilization?: number;
  checkpoint_frequency?: number;
  retry_rate?: number;
  recovery_success?: number;
  lease_expirations?: number;
  parallelism_efficiency?: number;
  task_count?: number;
  ready_tasks?: number;
  running_tasks?: number;
  blocked_tasks?: number;
  completed_tasks?: number;
  failed_tasks?: number;
  assignment_count?: number;
  active_assignments?: number;
  active_reservations?: number;
  recovery_reports?: number;
  manual_review_required?: number;
  average_queue_seconds?: number | null;
  average_assignment_duration_seconds?: number | null;
  mission_duration_seconds?: number | null;
};

type RuntimeEvent = {
  event_id?: string;
  sequence?: number;
  event_type?: string;
  payload?: Record<string, unknown>;
  occurred_at?: string;
};

type EvidenceItem = {
  id: string;
  task_id?: string | null;
  evidence_type: string;
  status: string;
  summary: string;
  payload?: {
    tool?: string;
    input_summary?: string;
    output_summary?: string;
    duration_ms?: number | null;
    status?: string;
    error_class?: string | null;
    audit_id?: string | null;
    payload?: Record<string, unknown>;
  };
  trust_level?: string;
  created_at?: string;
};

type VerificationRun = {
  id: string;
  verification_type: string;
  status: string;
  command?: string | null;
  result?: Record<string, any>;
  evidence_id?: string | null;
  started_at?: string;
  finished_at?: string | null;
};

type WorkspaceSnapshot = {
  organizations?: Array<{ name: string; status: string }>;
  repositories?: Array<{ name: string; status: string; local_workspace_path?: string; repository_root?: string; metadata?: Record<string, any> }>;
  context?: { current_mission?: { title?: string; status?: string; progress?: number } | null };
};

type RuntimeObservabilitySnapshot = {
  mission?: { title?: string; status?: string; duration_seconds?: number | null };
  timeline?: RuntimeEvent[];
  workers?: Array<{ worker_id: string; role: string; status: string; current_task_key?: string | null; assignment_status?: string | null; heartbeat_age_seconds?: number | null }>;
  reservations?: Array<{ reservation_id: string; task_key?: string | null; path_pattern: string; reservation_mode: string; status: string }>;
  dag?: {
    nodes?: Array<{ task_id: string; task_key: string; title: string; status: string; blocked_reason?: string | null; assignment_status?: string | null }>;
    edges?: Array<{ from_task_key?: string | null; to_task_key?: string | null; dependency_type: string }>;
  };
  recovery?: Array<{ assignment_id: string; task_key?: string | null; status?: string; local_stage?: string; repository_state?: string; recommended_action?: string }>;
  metrics?: RuntimeMetrics;
};

type ReleaseGateSnapshot = {
  allowed: boolean;
  subject_type: string;
  subject_id: string;
  readiness_status: string;
  score: number;
  blockers: string[];
  warnings: string[];
  required_actions: string[];
  checked_at?: string | null;
};

type MissionControlData = {
  metrics: RuntimeMetrics;
  events: RuntimeEvent[];
  evidence: EvidenceItem[];
  workspace: WorkspaceSnapshot;
  runtimeObservability: RuntimeObservabilitySnapshot;
  verificationRuns: VerificationRun[];
  changeSetContent?: Record<string, any> | null;
};

const FALLBACK_STATUS = [
  ['Repository', 'Healthy'],
  ['Tests', 'Passing'],
  ['Security Score', '99'],
  ['Deployment', 'Ready soon'],
  ['Branch', 'arceus/sprint-1'],
  ['AI Models', 'Healthy'],
];

function unwrap<T>(value: any, fallback: T): T {
  if (value?.data !== undefined) return value.data as T;
  if (Array.isArray(value?.items)) return value.items as T;
  return (value ?? fallback) as T;
}

function collection<T>(value: any): T[] {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  if (Array.isArray(value?.data?.items)) return value.data.items;
  return [];
}

function pct(value: number | undefined, fallback: number): string {
  const normalized = typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const percent = normalized <= 1 ? Math.round(normalized * 100) : Math.round(normalized);
  return `${Math.max(0, Math.min(100, percent))}%`;
}

function storedWorkspaceRoot(): string {
  if (typeof window === 'undefined') return '';
  try {
    const activeId = window.localStorage.getItem(ACTIVE_PROJECT_KEY) || '';
    const openIds = JSON.parse(window.localStorage.getItem(OPEN_PROJECTS_KEY) || '[]');
    const projects = JSON.parse(window.localStorage.getItem('nexus.code.projects') || '[]');
    const candidates = Array.isArray(projects) ? projects : [];
    const activeProject = candidates.find((project: CodeProject) => project.id === activeId)
      || candidates.find((project: CodeProject) => Array.isArray(openIds) && openIds.includes(project.id));
    return activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
  } catch {
    return '';
  }
}

function MissionControlPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || 'Build and operate a reliable AI engineering product.';
  const stack = searchParams.get('stack') || 'recommended';
  const [apiState, setApiState] = useState<ApiState>('loading');
  const [error, setError] = useState<string>('');
  const [createdMission, setCreatedMission] = useState<string>('');
  const [reviewActionMessage, setReviewActionMessage] = useState<string>('');
  const [localChangeSetReviewState, setLocalChangeSetReviewState] = useState<string>('');
  const [releaseGate, setReleaseGate] = useState<ReleaseGateSnapshot | null>(null);
  const [data, setData] = useState<MissionControlData>({
    metrics: {},
    events: [],
    evidence: [],
    workspace: {},
    runtimeObservability: {},
    verificationRuns: [],
    changeSetContent: null,
  });

  const loadMissionControl = useCallback(async () => {
    setApiState('loading');
    setError('');
    try {
      const missionId = createdMission || searchParams.get('mission_id') || '';
      const [metrics, events, evidence, workspace, runtimeObservability, verificationRuns] = await Promise.all([
        apiRequest('/api/v1/runtime/metrics').catch(() => ({})),
        apiRequest('/api/v1/runtime/events').catch(() => []),
        missionId ? apiRequest(`/api/v1/missions/${missionId}/evidence?evidence_type=tool_invocation&limit=20`).catch(() => []) : Promise.resolve([]),
        apiRequest('/api/v1/workspace').catch(() => ({})),
        missionId ? apiRequest(`/api/v1/task-runtime/missions/${missionId}/observability`).catch(() => ({})) : Promise.resolve({}),
        missionId ? apiRequest(`/api/v1/missions/${missionId}/verification-runs`).catch(() => []) : Promise.resolve([]),
      ]);
      const runtimeSnapshot = unwrap<RuntimeObservabilitySnapshot>(runtimeObservability, {});
      const runtimeEvents = collection<RuntimeEvent>(runtimeSnapshot.timeline);
      const effectiveEvents = (runtimeEvents.length ? runtimeEvents : collection<RuntimeEvent>(events)).slice(-8).reverse();
      const latestRecordedChange = effectiveEvents.find((event) => event.event_type === 'task.change_set.recorded' || event.event_type === 'arceus.task.change_set.recorded');
      const latestVersionId = String((latestRecordedChange?.payload as any)?.version_id || '');
      const changeSetVersionContent = latestVersionId
        ? await apiRequest(`/api/v1/artifact-versions/${latestVersionId}/content`).catch(() => null)
        : null;
      const changeSetContent = changeSetVersionContent ? unwrap<any>(changeSetVersionContent, changeSetVersionContent)?.content || null : null;
      setData({
        metrics: { ...unwrap<RuntimeMetrics>(metrics, {}), ...(runtimeSnapshot.metrics || {}) },
        events: effectiveEvents,
        evidence: collection<EvidenceItem>(evidence).slice(-8).reverse(),
        workspace: unwrap<WorkspaceSnapshot>(workspace, {}),
        runtimeObservability: runtimeSnapshot,
        verificationRuns: collection<VerificationRun>(verificationRuns),
        changeSetContent,
      });
      if (missionId) {
        const gateResult = await apiRequest('/api/v1/verification-engine/mission-control/release-gate', {
          method: 'POST',
          body: JSON.stringify({ mission_id: missionId, subject_type: 'release', subject_id: missionId }),
        }).catch(() => null);
        setReleaseGate(gateResult ? unwrap<ReleaseGateSnapshot>(gateResult, gateResult as ReleaseGateSnapshot) : null);
      } else {
        setReleaseGate(null);
      }
      setApiState('live');
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message} (${err.status})` : err instanceof Error ? err.message : 'Mission APIs are offline.';
      setError(message);
      setApiState('offline');
    }
  }, [createdMission, searchParams]);

  useEffect(() => {
    void loadMissionControl();
  }, [loadMissionControl]);

  const changeSetEvents = data.events.filter((event) => event.event_type === 'task.change_set.recorded' || event.event_type === 'arceus.task.change_set.recorded');
  const latestEvidence = data.evidence[0];
  const latestChangeSet = changeSetEvents[0];
  const currentMissionId = createdMission || searchParams.get('mission_id') || '';
  const releaseGateReady = releaseGate?.allowed === true;
  const releaseGateBlocked = !!releaseGate && !releaseGate.allowed;

  const openWorkspace = () => {
    const params = new URLSearchParams();
    params.set('stage', 'workspace');
    params.set('stack', stack);
    if (createdMission) params.set('mission_id', createdMission);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/workspace?${params.toString()}`);
  };

  const productMission = {
    title: data.runtimeObservability.mission?.title || data.workspace.context?.current_mission?.title || idea,
    repositoryName: data.workspace.repositories?.[0]?.name || 'Active repository',
    status: data.runtimeObservability.mission?.status || data.workspace.context?.current_mission?.status || (apiState === 'live' ? 'running' : 'attention_required'),
    durationSeconds: data.runtimeObservability.mission?.duration_seconds ?? data.metrics.mission_duration_seconds,
    progress: data.workspace.context?.current_mission?.progress ?? (
      data.metrics.task_count ? (data.metrics.completed_tasks || 0) / data.metrics.task_count : 0.18
    ),
  };
  const productWorkers = (data.runtimeObservability.workers || []).map((worker) => ({
    workerId: worker.worker_id,
    role: worker.role,
    status: worker.status,
    currentTaskKey: worker.current_task_key,
    assignmentStatus: worker.assignment_status,
    heartbeatAgeSeconds: worker.heartbeat_age_seconds,
  }));
  const productTasks = (data.runtimeObservability.dag?.nodes || []).map((task) => ({
    taskId: task.task_id,
    taskKey: task.task_key,
    title: task.title,
    status: task.status,
    blockedReason: task.blocked_reason,
    assignmentStatus: task.assignment_status,
  }));
  const productEdges = (data.runtimeObservability.dag?.edges || []).map((edge) => ({
    fromTaskKey: edge.from_task_key,
    toTaskKey: edge.to_task_key,
    dependencyType: edge.dependency_type,
  }));
  const productEvents = (data.runtimeObservability.timeline?.length ? data.runtimeObservability.timeline : data.events).map((event) => ({
    eventId: event.event_id,
    eventType: event.event_type,
    occurredAt: event.occurred_at,
    payload: event.payload || {},
  }));
  const productLocks = (data.runtimeObservability.reservations || []).map((lock) => ({
    reservationId: lock.reservation_id,
    pathPattern: lock.path_pattern,
    reservationMode: lock.reservation_mode,
    status: lock.status,
    taskKey: lock.task_key,
  }));
  const productMetrics = {
    taskCount: data.metrics.task_count,
    completedTasks: data.metrics.completed_tasks,
    activeAssignments: data.metrics.active_assignments,
    readyTasks: data.metrics.ready_tasks,
    runningTasks: data.metrics.running_tasks,
    blockedTasks: data.metrics.blocked_tasks,
    activeReservations: data.metrics.active_reservations,
    recoveryReports: data.metrics.recovery_reports,
    manualReviewRequired: data.metrics.manual_review_required,
    averageQueueSeconds: data.metrics.average_queue_seconds,
    missionDurationSeconds: data.metrics.mission_duration_seconds,
    evidenceCount: data.evidence.length,
  };
  const productEvidence = data.evidence.map((item) => ({
    id: item.id,
    summary: item.summary,
    status: item.status,
    evidenceType: item.evidence_type,
    createdAt: item.created_at,
    tool: item.payload?.tool,
    inputSummary: item.payload?.input_summary,
    outputSummary: item.payload?.output_summary,
    durationMs: item.payload?.duration_ms,
    trustLevel: item.trust_level,
  }));
  const productRecovery = (data.runtimeObservability.recovery || []).map((item) => ({
    assignmentId: item.assignment_id,
    taskKey: item.task_key,
    status: item.status,
    localStage: item.local_stage,
    repositoryState: item.repository_state,
    recommendedAction: item.recommended_action,
  }));
  const artifactChangeSet = data.changeSetContent || {};
  const latestChangePayload = Object.keys(artifactChangeSet).length ? artifactChangeSet : latestChangeSet?.payload || {};
  const latestChangeTaskId = String((latestChangePayload as any).task_id || '');
  const latestChangeArtifactId = String((latestChangeSet?.payload as any)?.artifact_id || '');
  const latestChangeArtifactVersionId = String((latestChangeSet?.payload as any)?.version_id || '');
  const payloadChanges = Array.isArray((latestChangePayload as any).changes)
    ? (latestChangePayload as any).changes
    : Array.isArray((latestEvidence?.payload?.payload as any)?.changes)
      ? (latestEvidence?.payload?.payload as any).changes
      : [];
  const productChangeSet = {
    title: String((latestChangePayload as any).title || 'Mission Change Set'),
    summary: latestChangeSet
      ? 'Repository changes recorded by the desktop worker runtime.'
      : 'No recorded patch yet. Run an implementation task to produce a reviewable change set.',
    reviewState: localChangeSetReviewState || String((latestChangePayload as any).review_state || (latestChangeSet ? 'recorded' : 'not_created')),
    rollbackAvailable: payloadChanges.some((change: any) => Boolean(change.rollback_payload) || Boolean(change.rollback_snapshot_id)) || String((latestChangePayload as any).review_state || '').includes('applied'),
    files: payloadChanges.length
      ? payloadChanges.map((change: any) => ({
          path: String(change.path || change.new_path || change.old_path || 'unknown'),
          operation: String(change.operation || 'modify'),
          additions: Number(change.additions || change.metadata?.additions || 0),
          deletions: Number(change.deletions || change.metadata?.deletions || 0),
          risk: String(change.risk || 'medium'),
          reviewRequired: Boolean(change.review_required),
          applied: Boolean(change.applied),
          rollbackSnapshotId: change.rollback_snapshot_id || null,
          diff: change.diff || null,
        }))
      : latestChangeSet
        ? [{
            path: String((latestChangePayload as any).path || 'recorded-change-set'),
            operation: 'modify',
            additions: Number((latestChangePayload as any).additions || (latestChangePayload as any).change_count || 0),
            deletions: Number((latestChangePayload as any).deletions || 0),
            risk: 'medium',
            reviewRequired: String((latestChangePayload as any).review_state || '').includes('review'),
            applied: String((latestChangePayload as any).review_state || '') === 'applied',
            rollbackSnapshotId: null,
            diff: null,
          }]
        : [],
  };
  const productVerification = data.verificationRuns.map((run) => ({
    id: run.id,
    label: run.verification_type.replace(/_/g, ' '),
    status: run.status,
    command: run.command,
    summary: typeof run.result?.summary === 'string' ? run.result.summary : undefined,
    evidenceId: run.evidence_id,
    durationMs: typeof run.result?.duration_ms === 'number' ? run.result.duration_ms : undefined,
  }));
  const productNotifications = [
    ...(apiState === 'offline'
      ? [{ id: 'api-offline', tone: 'warning' as const, title: 'Runtime APIs offline', detail: 'Mission Control is showing the latest recoverable local view.' }]
      : []),
    ...(releaseGateBlocked
      ? [{ id: 'release-blocked', tone: 'warning' as const, title: 'Release gate blocked', detail: releaseGate?.blockers[0] || releaseGate?.required_actions[0] || 'Run release readiness checks.' }]
      : []),
    ...(releaseGateReady
      ? [{ id: 'release-ready', tone: 'success' as const, title: 'Release gate passed', detail: 'PR and deployment actions can be enabled.' }]
      : []),
  ];

  const reviewChangeSet = async (action: 'approve' | 'reject' | 'rollback') => {
    setError('');
    setReviewActionMessage('');
    if (!currentMissionId || !latestChangeTaskId) {
      setError('No actionable change set is linked to this mission yet.');
      return;
    }
    try {
      const workspaceRoot =
        searchParams.get('workspace_root')
        || searchParams.get('repository_root')
        || searchParams.get('root_path')
        || String((latestChangePayload as any).metadata?.workspace_root || (latestChangePayload as any).metadata?.repository_root || '')
        || data.workspace.repositories?.[0]?.local_workspace_path
        || data.workspace.repositories?.[0]?.repository_root
        || data.workspace.repositories?.[0]?.metadata?.local_workspace_path
        || storedWorkspaceRoot();
      let response;
      if (action === 'approve') {
        await apiRequest(`/api/v1/missions/${currentMissionId}/tasks/${latestChangeTaskId}/change-set/review`, {
          method: 'POST',
          body: JSON.stringify({
            action,
            artifact_id: latestChangeArtifactId || null,
            artifact_version_id: latestChangeArtifactVersionId || null,
            reason: 'Approved from Mission Control patch review.',
          }),
        });
        response = await apiRequest(`/api/v1/missions/${currentMissionId}/tasks/${latestChangeTaskId}/change-set/execute`, {
          method: 'POST',
          body: JSON.stringify({
            action: 'apply',
            artifact_id: latestChangeArtifactId || null,
            artifact_version_id: latestChangeArtifactVersionId || null,
            workspace_root: workspaceRoot || null,
            reason: 'Apply approved change set from Mission Control.',
            metadata: { workspace_root: workspaceRoot || null },
          }),
        });
      } else if (action === 'rollback') {
        response = await apiRequest(`/api/v1/missions/${currentMissionId}/tasks/${latestChangeTaskId}/change-set/execute`, {
          method: 'POST',
          body: JSON.stringify({
            action,
            artifact_id: latestChangeArtifactId || null,
            artifact_version_id: latestChangeArtifactVersionId || null,
            workspace_root: workspaceRoot || null,
            reason: 'Rollback from Mission Control patch review.',
            metadata: { workspace_root: workspaceRoot || null },
          }),
        });
      } else {
        response = await apiRequest(`/api/v1/missions/${currentMissionId}/tasks/${latestChangeTaskId}/change-set/review`, {
          method: 'POST',
          body: JSON.stringify({
            action,
            artifact_id: latestChangeArtifactId || null,
            artifact_version_id: latestChangeArtifactVersionId || null,
            reason: 'Rejected from Mission Control patch review.',
          }),
        });
      }
      const result = unwrap<any>(response, response);
      setLocalChangeSetReviewState(String(result.review_state || action));
      setReviewActionMessage(`Change set ${action === 'approve' ? 'approved and applied' : action === 'reject' ? 'rejected' : 'rolled back'} for ${result.affected_files?.length || productChangeSet.files.length} file(s).`);
      await loadMissionControl();
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message} (${err.status})` : err instanceof Error ? err.message : 'Could not update change-set review state.';
      setError(message);
    }
  };

  return (
    <main className={styles.operations}>
      <section className={styles.window} aria-label="Arceus Code engineering operations center">
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <span>A</span>
            <div>
              <strong>Arceus Code</strong>
              <small>{data.workspace.context?.current_mission?.title || 'Mission Control'}</small>
            </div>
          </div>
          <div className={styles.sprintMeta}>
            <span>Runtime <b>{apiState === 'live' ? 'Live' : apiState === 'loading' ? 'Loading' : 'Offline'}</b></span>
            <span>Progress <b>{pct(data.workspace.context?.current_mission?.progress, 0.18)}</b></span>
            <i><em style={{ width: pct(data.workspace.context?.current_mission?.progress, 0.18) }} /></i>
          </div>
          <label className={styles.search}>
            <Search size={17} />
            <input aria-label="Search everything" placeholder="Search runtime, missions, product, automation..." />
          </label>
          <div className={styles.actions}>
            <button type="button" aria-label="Refresh mission APIs" onClick={() => void loadMissionControl()}><RefreshCw size={18} /></button>
            <button type="button" aria-label="Notifications"><Bell size={18} /></button>
            <button type="button" aria-label="Profile"><UserRound size={18} /></button>
            <span data-state={apiState}><Cloud size={15} /> {apiState === 'live' ? 'Synced' : apiState === 'loading' ? 'Checking' : 'Local view'}</span>
          </div>
        </header>

        {error && <div className={styles.errorBanner}>{error}</div>}
        {createdMission && <div className={styles.successBanner}>Durable mission created: {createdMission}</div>}
        {reviewActionMessage && <div className={styles.successBanner}>{reviewActionMessage}</div>}

        <section className={styles.hero}>
          <p><span /> {Math.max(productWorkers.length, 3)} Engineers Active</p>
          <h1>Engineering Operations Center</h1>
          <strong>Your AI engineering organization is building from real mission APIs.</strong>
        </section>

        <MissionControlProductView
          mission={productMission}
          workers={productWorkers}
          tasks={productTasks}
          edges={productEdges}
          events={productEvents}
          locks={productLocks}
          metrics={productMetrics}
          evidence={productEvidence}
          recovery={productRecovery}
          changeSet={productChangeSet}
          verification={productVerification}
          notifications={productNotifications}
          onRefresh={() => void loadMissionControl()}
          onOpenWorkspace={openWorkspace}
          onApproveAll={() => void reviewChangeSet('approve')}
          onRejectAll={() => void reviewChangeSet('reject')}
          onRollback={() => void reviewChangeSet('rollback')}
        />

        <footer className={styles.statusBar}>
          {FALLBACK_STATUS.map(([label, value]) => (
            <span key={label}><Check size={13} /><b>{label}</b>{value}</span>
          ))}
        </footer>
      </section>
    </main>
  );
}

export default function MissionControlPage() {
  return (
    <Suspense fallback={null}>
      <MissionControlPageContent />
    </Suspense>
  );
}
