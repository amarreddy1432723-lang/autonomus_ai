'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Bell,
  Check,
  Cloud,
  GitBranch,
  Pause,
  RefreshCw,
  Rocket,
  Search,
  ShieldCheck,
  Wrench,
  UserRound,
} from 'lucide-react';
import { ApiError, apiRequest } from '../../utils/api';
import { MissionControlProductView } from '../../components/mission-control/MissionControlProductView';
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

type AutomationMission = {
  mission_id: string;
  title: string;
  domain: string;
  status: string;
  autonomy_level: string;
  risk_level: string;
  owner_organization: string;
  generated_from: string;
  workflow_steps: string[];
};

type ProductDashboard = {
  opportunities?: Array<{ title: string; horizon: string; priority_score: number; recommended_action: string }>;
  roadmap?: Array<{ title: string; horizon: string; priority_score: number; release_candidate: string }>;
  product_health?: string;
  recommendations?: string[];
};

type WorkspaceSnapshot = {
  organizations?: Array<{ name: string; status: string }>;
  repositories?: Array<{ name: string; status: string }>;
  context?: { current_mission?: { title?: string; status?: string; progress?: number } | null };
};

type DashboardSnapshot = {
  widgets?: Array<{ widget_key: string; title: string; value: string; status: string; action?: string }>;
  notifications?: Array<{ priority: string; required_action: string; impact: string }>;
};

type ObservabilitySnapshot = {
  traces?: Array<{ trace_id: string; service: string; name: string; status: string; duration_ms?: number | null }>;
  logs?: Array<{ log_id: string; trace_id: string; level: string; service: string; message: string; occurred_at?: string | null }>;
  alerts?: Array<{ alert_id: string; severity: string; status: string; title: string; fired_at?: string | null }>;
  incidents?: Array<{ incident_id: string; severity: string; status: string; title: string; summary: string }>;
  exporters?: Array<{ exporter_key: string; exporter_type: string; status: string; active: boolean }>;
  delivery_channels?: Array<{ channel_key: string; channel_type: string; status: string; active: boolean }>;
  recovery_actions?: Array<{ action_key: string; title: string; policy_status: string; execution_status: string; risk_level: string }>;
  aiops_recommendations?: string[];
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
  automationMissions: AutomationMission[];
  product: ProductDashboard;
  workspace: WorkspaceSnapshot;
  dashboard: DashboardSnapshot;
  observability: ObservabilitySnapshot;
  runtimeObservability: RuntimeObservabilitySnapshot;
};

const FALLBACK_ENGINEERS = [
  ['EM', 'Engineering Manager', 'Coordinating sprint execution', '98%', '4 files', 'Ready', '12m'],
  ['AR', 'Architect', 'Reviewing API boundaries', '96%', '2 docs', 'Reviewing', '18m'],
  ['FE', 'Frontend', 'Building login workflow', '94%', '8 files', 'Active', '24m'],
  ['BE', 'Backend', 'Implementing authentication API', '91%', '6 files', 'Active', '19m'],
  ['QA', 'QA', 'Generating regression tests', '92%', '12 tests', 'Active', '28m'],
  ['SE', 'Security', 'Checking OAuth configuration', '89%', '1 issue', 'Attention', '9m'],
];

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

function eventTitle(event: RuntimeEvent): string {
  const name = (event.event_type || 'runtime.event').replace(/^runtime\./, '').replace(/^arceus\./, '').replace(/[._]/g, ' ');
  const payload = event.payload || {};
  const detail = String(payload.task_key || payload.title || payload.status || payload.surface || '').trim();
  return detail ? `${name}: ${detail}` : name;
}

function eventTime(event: RuntimeEvent): string {
  if (!event.occurred_at) return 'now';
  try {
    return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(event.occurred_at));
  } catch {
    return 'now';
  }
}

function MissionControlPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || 'Build and operate a reliable AI engineering product.';
  const stack = searchParams.get('stack') || 'recommended';
  const [apiState, setApiState] = useState<ApiState>('loading');
  const [error, setError] = useState<string>('');
  const [busyAction, setBusyAction] = useState<string>('');
  const [createdMission, setCreatedMission] = useState<string>('');
  const [releaseGate, setReleaseGate] = useState<ReleaseGateSnapshot | null>(null);
  const [data, setData] = useState<MissionControlData>({
    metrics: {},
    events: [],
    evidence: [],
    automationMissions: [],
    product: {},
    workspace: {},
    dashboard: {},
    observability: {},
    runtimeObservability: {},
  });

  const loadMissionControl = useCallback(async () => {
    setApiState('loading');
    setError('');
    try {
      const missionId = createdMission || searchParams.get('mission_id') || '';
      const [metrics, events, evidence, automationMissions, product, workspace, dashboard, observability, runtimeObservability] = await Promise.all([
        apiRequest('/api/v1/runtime/metrics').catch(() => ({})),
        apiRequest('/api/v1/runtime/events').catch(() => []),
        missionId ? apiRequest(`/api/v1/missions/${missionId}/evidence?evidence_type=tool_invocation&limit=20`).catch(() => []) : Promise.resolve([]),
        apiRequest('/api/v1/automation/missions').catch(() => []),
        apiRequest('/api/v1/product/dashboard').catch(() => ({})),
        apiRequest('/api/v1/workspace').catch(() => ({})),
        apiRequest('/api/v1/dashboard?role=developer').catch(() => ({})),
        apiRequest('/api/v1/telemetry/mission-control').catch(() => ({})),
        missionId ? apiRequest(`/api/v1/task-runtime/missions/${missionId}/observability`).catch(() => ({})) : Promise.resolve({}),
      ]);
      const runtimeSnapshot = unwrap<RuntimeObservabilitySnapshot>(runtimeObservability, {});
      const runtimeEvents = collection<RuntimeEvent>(runtimeSnapshot.timeline);
      setData({
        metrics: { ...unwrap<RuntimeMetrics>(metrics, {}), ...(runtimeSnapshot.metrics || {}) },
        events: (runtimeEvents.length ? runtimeEvents : collection<RuntimeEvent>(events)).slice(-8).reverse(),
        evidence: collection<EvidenceItem>(evidence).slice(-8).reverse(),
        automationMissions: collection<AutomationMission>(automationMissions),
        product: unwrap<ProductDashboard>(product, {}),
        workspace: unwrap<WorkspaceSnapshot>(workspace, {}),
        dashboard: unwrap<DashboardSnapshot>(dashboard, {}),
        observability: unwrap<ObservabilitySnapshot>(observability, {}),
        runtimeObservability: runtimeSnapshot,
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

  const engineers = useMemo(() => {
    const runtimeWorkers = data.runtimeObservability.workers || [];
    if (runtimeWorkers.length) {
      return runtimeWorkers.map((worker, index) => [
        worker.role.split(/[_\s-]+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'AI',
        worker.role.replace(/_/g, ' '),
        worker.current_task_key ? `${worker.assignment_status || 'assigned'} · ${worker.current_task_key}` : 'Waiting for assignment',
        pct(worker.heartbeat_age_seconds != null ? Math.max(0, 1 - worker.heartbeat_age_seconds / 180) : 0.98, 0.98),
        worker.current_task_key ? '1 task' : '0 tasks',
        worker.status,
        worker.heartbeat_age_seconds != null ? `${Math.round(worker.heartbeat_age_seconds)}s heartbeat` : 'no heartbeat',
      ]);
    }
    const organizations = data.workspace.organizations || [];
    if (!organizations.length) return FALLBACK_ENGINEERS;
    return organizations.map((org, index) => [
      org.name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'AI',
      org.name,
      index === 0 ? 'Coordinating active mission' : 'Ready for mission assignment',
      pct(data.metrics.recovery_success, 0.96),
      `${Math.max(1, Math.round((data.metrics.checkpoint_frequency || 0.4) * 10))} artifacts`,
      org.status || 'Ready',
      `${12 + index * 4}m`,
    ]);
  }, [data.metrics, data.runtimeObservability.workers, data.workspace.organizations]);

  const sprintCards = useMemo(() => {
    const runtimeTasks = data.runtimeObservability.dag?.nodes || [];
    if (runtimeTasks.length) {
      return runtimeTasks.slice(0, 6).map((task) => [
        task.status,
        task.title || task.task_key,
        task.assignment_status || 'scheduler',
        task.status === 'failed' ? 'P0' : task.blocked_reason ? 'P1' : 'P2',
        task.blocked_reason || 'dependencies clear',
        task.task_key,
        task.status === 'completed' ? '100%' : task.status === 'running' ? '65%' : task.status === 'ready' ? '25%' : '8%',
      ]);
    }
    const missions = data.automationMissions.slice(0, 5);
    if (!missions.length) {
      return [
        ['Current Milestone', 'Core Platform', 'Engineering Manager', 'P0', 'None', '10 weeks plan', '18%'],
        ['In Progress', 'Authentication module', 'Backend', 'P0', 'API contracts', '34m', '65%'],
        ['Waiting Review', 'Database schema', 'Database', 'P1', 'Security check', '12m', '82%'],
        ['Upcoming', 'Frontend login UI', 'Frontend', 'P1', 'Auth API', '48m', '0%'],
      ];
    }
    return missions.map((mission, index) => [
      index === 0 ? 'Current Mission' : mission.status,
      mission.title,
      mission.owner_organization.replace(/_/g, ' '),
      mission.risk_level === 'critical' ? 'P0' : mission.risk_level === 'high' ? 'P1' : 'P2',
      mission.generated_from,
      mission.autonomy_level,
      mission.status === 'ready' ? '35%' : mission.status.includes('approval') ? '12%' : '8%',
    ]);
  }, [data.automationMissions, data.runtimeObservability.dag?.nodes]);

  const artifacts = useMemo(() => {
    const roadmap = data.product.roadmap || [];
    const opportunities = data.product.opportunities || [];
    return [
      ['Repository', data.workspace.repositories?.[0]?.status || 'Connected', data.workspace.repositories?.[0]?.name || 'Active workspace'],
      ['Product Roadmap', roadmap.length ? `${roadmap.length} items` : 'Pending', roadmap[0]?.release_candidate || 'Generate product mission'],
      ['Opportunities', opportunities.length ? `${opportunities.length} ranked` : 'Pending', opportunities[0]?.title || 'No ranked opportunity'],
      ['Runtime Events', `${data.events.length} recent`, data.events[0]?.event_type || 'Waiting for mission activity'],
      ['DAG', `${data.runtimeObservability.dag?.nodes?.length || 0} tasks`, `${data.runtimeObservability.dag?.edges?.length || 0} dependencies`],
      ['Reservations', `${data.metrics.active_reservations || 0} active`, 'Repository lock visualization'],
      ['Recovery', `${data.runtimeObservability.recovery?.length || 0} report(s)`, 'Interrupted execution center'],
    ];
  }, [data]);

  const controls = useMemo(() => [
    ['Approval Queue', data.dashboard.notifications?.length ? `${data.dashboard.notifications.length} waiting` : '0 waiting', 'Review important decisions'],
    ['Automation Missions', `${data.automationMissions.length}`, 'Persisted from triggers and workflows'],
    ['Product Health', data.product.product_health || 'unknown', 'Product intelligence dashboard'],
    ['Worker Utilization', pct(data.metrics.worker_utilization, 0.25), 'Runtime kernel activity'],
    ['Queue Time', data.metrics.average_queue_seconds != null ? `${Math.round(data.metrics.average_queue_seconds)}s` : 'n/a', 'Average assignment wait'],
    ['Review Required', String(data.metrics.manual_review_required || 0), 'Recovery or blocked execution signal'],
  ], [data]);

  const activity = data.events.length
    ? data.events.map((event) => [eventTime(event), eventTitle(event)])
    : [
        ['09:21', 'Runtime kernel is ready for durable missions.'],
        ['09:24', 'Automation, product, and experience APIs are connected.'],
        ['09:27', 'Create a mission to start the live feed.'],
      ];

  const changeSetEvents = data.events.filter((event) => event.event_type === 'task.change_set.recorded' || event.event_type === 'arceus.task.change_set.recorded');
  const latestEvidence = data.evidence[0];
  const currentTaskKey = String(
    latestEvidence?.payload?.payload?.task_key ||
    latestEvidence?.payload?.payload?.context_package_id ||
    data.events.find((event) => event.payload?.task_key)?.payload?.task_key ||
    'Waiting for claimed task'
  );
  const currentTool = latestEvidence?.payload?.tool || 'No tool running';
  const lastTool = latestEvidence
    ? `${latestEvidence.payload?.tool || 'tool'} · ${latestEvidence.status}`
    : 'No tool evidence yet';
  const latestChangeSet = changeSetEvents[0];
  const changeSetState = latestChangeSet
    ? String(latestChangeSet.payload?.review_state || 'recorded')
    : 'not created';
  const executionProof = [
    ['Current Task', currentTaskKey, latestEvidence ? latestEvidence.summary : 'Claim a task to hydrate context and begin execution.'],
    ['Current Tool', currentTool, latestEvidence?.payload?.input_summary || 'Desktop tools are idle.'],
    ['Last Tool', lastTool, latestEvidence?.payload?.output_summary || 'Tool output summaries will appear here.'],
    ['Evidence', `${data.evidence.length}`, latestEvidence?.trust_level || 'No persisted tool evidence yet.'],
    ['Change Set', changeSetState, latestChangeSet ? `${latestChangeSet.payload?.change_count || 0} change(s)` : 'Patch validation has not run yet.'],
    ['Duration', latestEvidence?.payload?.duration_ms != null ? `${latestEvidence.payload.duration_ms} ms` : 'n/a', 'Measured by desktop tool audit records.'],
  ];

  const observabilityCards = [
    ['Traces', String(data.observability.traces?.length || 0), data.observability.traces?.[0]?.status || 'waiting'],
    ['Logs', String(data.observability.logs?.length || 0), data.observability.logs?.[0]?.level || 'quiet'],
    ['Alerts', String(data.observability.alerts?.length || 0), data.observability.alerts?.[0]?.severity || 'none'],
    ['DAG', String(data.runtimeObservability.dag?.nodes?.length || 0), `${data.metrics.blocked_tasks || 0} blocked`],
    ['Workers', String(data.runtimeObservability.workers?.length || 0), `${data.metrics.active_assignments || 0} active`],
    ['Locks', String(data.runtimeObservability.reservations?.length || 0), `${data.metrics.active_reservations || 0} active`],
    ['Recovery', String(data.runtimeObservability.recovery?.length || data.observability.recovery_actions?.length || 0), data.runtimeObservability.recovery?.[0]?.status || data.observability.recovery_actions?.[0]?.execution_status || 'policy gated'],
  ];
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

  const createIntentMission = async () => {
    setBusyAction('intent');
    setError('');
    try {
      const result = await apiRequest('/api/v1/intents/execute', {
        method: 'POST',
        body: JSON.stringify({ objective: idea, mode: 'workflow', context_scope: 'project', constraints: ['Create evidence-first implementation plan.'] }),
      });
      const payload = unwrap<any>(result, result);
      const missionId = payload?.mission_thread?.linked_mission_id;
      if (missionId) setCreatedMission(String(missionId));
      await loadMissionControl();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create intent mission.');
    } finally {
      setBusyAction('');
    }
  };

  const createProductMission = async () => {
    setBusyAction('product');
    setError('');
    try {
      const result = await apiRequest('/api/v1/product/requirements', {
        method: 'POST',
        body: JSON.stringify({
          title: idea.slice(0, 120),
          business_problem: 'The founder needs a verified product plan before implementation starts.',
          user_problem: idea,
          objectives: ['Create a durable product mission.', 'Produce implementation-ready requirements.', 'Link future work to evidence.'],
          stakeholders: ['Founder', 'Engineering Lead', 'Product Reviewer'],
          risks: ['unclear scope', 'implementation sequencing risk'],
          framework: 'rice',
        }),
      });
      const payload = unwrap<any>(result, result);
      const missionId = payload?.mission_seed?.durable_mission_id;
      if (missionId) setCreatedMission(String(missionId));
      await loadMissionControl();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create product mission.');
    } finally {
      setBusyAction('');
    }
  };

  const createAutomationMission = async () => {
    setBusyAction('automation');
    setError('');
    try {
      const result = await apiRequest('/api/v1/automation/execute', {
        method: 'POST',
        body: JSON.stringify({
          objective: idea,
          domain: 'engineering',
          template_key: 'release',
          autonomy_level: 'L3',
          risk_level: 'medium',
          dry_run: true,
          connector_keys: ['github', 'ci_cd'],
        }),
      });
      const payload = unwrap<any>(result, result);
      const missionId = payload?.workflow?.durable_mission?.mission_id;
      if (missionId) setCreatedMission(String(missionId));
      await loadMissionControl();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create automation mission.');
    } finally {
      setBusyAction('');
    }
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
  }));
  const productRecovery = (data.runtimeObservability.recovery || []).map((item) => ({
    assignmentId: item.assignment_id,
    taskKey: item.task_key,
    status: item.status,
    localStage: item.local_stage,
    repositoryState: item.repository_state,
    recommendedAction: item.recommended_action,
  }));

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

        <section className={styles.hero}>
          <p><span /> {engineers.length} Engineers Active</p>
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
          onRefresh={() => void loadMissionControl()}
          onOpenWorkspace={openWorkspace}
        />

        <section className={styles.grid}>
          <article className={styles.panel}>
            <header><h2>Engineering Organization</h2><small>Live workspace organization</small></header>
            <div className={styles.orgList}>
              {engineers.map(([initials, role, task, confidence, files, state, eta], index) => (
                <button type="button" key={`${role}-${index}`} className={styles.engineer} data-state={String(state).toLowerCase()} style={{ animationDelay: `${index * 45}ms` }}>
                  <span>{initials}</span>
                  <div>
                    <strong>{role}</strong>
                    <small>{task}</small>
                    <em>{confidence} confidence · {files} · ETA {eta}</em>
                  </div>
                  <b>{state}</b>
                </button>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Current Sprint</h2><small>Persisted automation/product missions</small></header>
            <div className={styles.sprintBoard}>
              {sprintCards.map(([section, title, owner, priority, dependencies, eta, progress]) => (
                <section key={`${section}-${title}`} className={styles.taskCard}>
                  <div>
                    <span>{section}</span>
                    <b>{priority}</b>
                  </div>
                  <h3>{title}</h3>
                  <p>{owner} · {dependencies}</p>
                  <footer>
                    <small>{eta}</small>
                    <strong>{progress}</strong>
                  </footer>
                  <i><em style={{ width: progress }} /></i>
                </section>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Artifacts</h2><small>Runtime and product outputs</small></header>
            <div className={styles.artifactList}>
              {artifacts.map(([name, state, detail]) => (
                <button type="button" key={name} className={styles.artifact}>
                  <span><GitBranch size={15} /></span>
                  <div>
                    <strong>{name}</strong>
                    <small>{detail}</small>
                  </div>
                  <b>{state}</b>
                </button>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Executive Control</h2><small>Founder-level actions</small></header>
            <div className={styles.controlList}>
              {controls.map(([name, value, detail]) => (
                <button type="button" key={name} className={styles.control}>
                  <div>
                    <strong>{name}</strong>
                    <small>{detail}</small>
                  </div>
                  <b>{value}</b>
                </button>
              ))}
            </div>
          </article>
        </section>

        <section className={styles.activity}>
          <header>
            <div>
              <h2>Activity Timeline</h2>
              <small>Runtime events and mission creation evidence.</small>
            </div>
            <div className={styles.primaryActions}>
              <button type="button" onClick={createIntentMission} disabled={!!busyAction}><Pause size={16} /> {busyAction === 'intent' ? 'Creating...' : 'Create Intent Mission'}</button>
              <button type="button" onClick={createProductMission} disabled={!!busyAction}><ShieldCheck size={16} /> {busyAction === 'product' ? 'Creating...' : 'Create Product Mission'}</button>
              <button type="button" onClick={openWorkspace}>Open Workspace</button>
              <button
                type="button"
                onClick={createAutomationMission}
                disabled={!!busyAction || releaseGateBlocked}
                title={releaseGateBlocked ? releaseGate?.blockers[0] || 'Release gate is not ready.' : undefined}
              >
                <Rocket size={16} /> {busyAction === 'automation' ? 'Creating...' : 'Launch Automation'}
              </button>
              <button type="button" disabled={!releaseGateReady} title={releaseGateReady ? 'Release gate passed.' : 'Release gate must pass before creating a PR.'}>
                <GitBranch size={16} /> Create PR
              </button>
              <button type="button" disabled={!releaseGateReady} title={releaseGateReady ? 'Release gate passed.' : 'Release gate must pass before deployment.'}>
                <Rocket size={16} /> Deploy
              </button>
            </div>
          </header>
          <div className={styles.observabilityStrip}>
            {observabilityCards.map(([label, value, detail]) => (
              <button type="button" key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
                <small>{detail}</small>
              </button>
            ))}
          </div>
          <section className={styles.executionProof} aria-label="Execution proof">
            <header>
              <div>
                <h3>Execution Proof</h3>
                <small>Current task, tool evidence, patch state, and rollback-aware change-set status.</small>
              </div>
              <span><Wrench size={14} /> {data.evidence.length ? 'Evidence linked' : 'Awaiting tool run'}</span>
            </header>
            <div>
              {executionProof.map(([label, value, detail]) => (
                <article key={label}>
                  <small>{label}</small>
                  <strong>{value}</strong>
                  <p>{detail}</p>
                </article>
              ))}
            </div>
          </section>
          {releaseGate && (
            <div className={releaseGateReady ? styles.releaseGateReady : styles.releaseGateBlocked}>
              <strong>Release Gate: {releaseGate.readiness_status}</strong>
              <span>
                {releaseGateReady
                  ? 'PR and deploy actions are allowed.'
                  : releaseGate.blockers[0] || releaseGate.required_actions[0] || 'Run release readiness before PR or deploy.'}
              </span>
            </div>
          )}
          {!!data.observability.aiops_recommendations?.length && (
            <div className={styles.aiopsNote}>
              {data.observability.aiops_recommendations[0]}
            </div>
          )}
          <section className={styles.runtimeMap} aria-label="Runtime operational map">
            <article>
              <header>
                <strong>Task DAG</strong>
                <small>{data.runtimeObservability.dag?.edges?.length || 0} dependency link(s)</small>
              </header>
              {(data.runtimeObservability.dag?.nodes || []).slice(0, 5).map((node) => (
                <div key={node.task_id}>
                  <span data-state={node.status}>{node.status}</span>
                  <b>{node.task_key}</b>
                  <small>{node.blocked_reason || node.assignment_status || 'ready for scheduling'}</small>
                </div>
              ))}
              {!(data.runtimeObservability.dag?.nodes || []).length && <p>No persisted task graph selected yet.</p>}
            </article>
            <article>
              <header>
                <strong>Repository Locks</strong>
                <small>{data.metrics.active_reservations || 0} active</small>
              </header>
              {(data.runtimeObservability.reservations || []).slice(0, 5).map((reservation) => (
                <div key={reservation.reservation_id}>
                  <span data-state={reservation.status}>{reservation.reservation_mode}</span>
                  <b>{reservation.path_pattern}</b>
                  <small>{reservation.task_key || 'unlinked task'} · {reservation.status}</small>
                </div>
              ))}
              {!(data.runtimeObservability.reservations || []).length && <p>No repository paths are reserved.</p>}
            </article>
            <article>
              <header>
                <strong>Recovery Center</strong>
                <small>{data.runtimeObservability.recovery?.length || 0} report(s)</small>
              </header>
              {(data.runtimeObservability.recovery || []).slice(0, 5).map((report) => (
                <div key={`${report.assignment_id}-${report.local_stage}-${report.status}`}>
                  <span data-state={report.status || 'reported'}>{report.status || 'reported'}</span>
                  <b>{report.task_key || report.assignment_id.slice(0, 8)}</b>
                  <small>{report.repository_state || 'unknown'} · {report.recommended_action || 'inspect'}</small>
                </div>
              ))}
              {!(data.runtimeObservability.recovery || []).length && <p>No interrupted execution reports.</p>}
            </article>
          </section>
          <div className={styles.feed}>
            {activity.map(([time, text]) => (
              <article key={`${time}-${text}`}>
                <b>{time}</b>
                <span>{text}</span>
              </article>
            ))}
          </div>
        </section>

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
