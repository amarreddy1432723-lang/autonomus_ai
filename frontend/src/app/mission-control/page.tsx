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
  UserRound,
} from 'lucide-react';
import { ApiError, apiRequest } from '../../utils/api';
import styles from './MissionControl.module.css';

type ApiState = 'loading' | 'live' | 'offline';

type RuntimeMetrics = {
  worker_utilization?: number;
  checkpoint_frequency?: number;
  retry_rate?: number;
  recovery_success?: number;
  lease_expirations?: number;
  parallelism_efficiency?: number;
};

type RuntimeEvent = {
  event_id?: string;
  sequence?: number;
  event_type?: string;
  payload?: Record<string, unknown>;
  occurred_at?: string;
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

type MissionControlData = {
  metrics: RuntimeMetrics;
  events: RuntimeEvent[];
  automationMissions: AutomationMission[];
  product: ProductDashboard;
  workspace: WorkspaceSnapshot;
  dashboard: DashboardSnapshot;
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
  const [data, setData] = useState<MissionControlData>({
    metrics: {},
    events: [],
    automationMissions: [],
    product: {},
    workspace: {},
    dashboard: {},
  });

  const loadMissionControl = useCallback(async () => {
    setApiState('loading');
    setError('');
    try {
      const [metrics, events, automationMissions, product, workspace, dashboard] = await Promise.all([
        apiRequest('/api/v1/runtime/metrics').catch(() => ({})),
        apiRequest('/api/v1/runtime/events').catch(() => []),
        apiRequest('/api/v1/automation/missions').catch(() => []),
        apiRequest('/api/v1/product/dashboard').catch(() => ({})),
        apiRequest('/api/v1/workspace').catch(() => ({})),
        apiRequest('/api/v1/dashboard?role=developer').catch(() => ({})),
      ]);
      setData({
        metrics: unwrap<RuntimeMetrics>(metrics, {}),
        events: collection<RuntimeEvent>(events).slice(-8).reverse(),
        automationMissions: collection<AutomationMission>(automationMissions),
        product: unwrap<ProductDashboard>(product, {}),
        workspace: unwrap<WorkspaceSnapshot>(workspace, {}),
        dashboard: unwrap<DashboardSnapshot>(dashboard, {}),
      });
      setApiState('live');
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message} (${err.status})` : err instanceof Error ? err.message : 'Mission APIs are offline.';
      setError(message);
      setApiState('offline');
    }
  }, []);

  useEffect(() => {
    void loadMissionControl();
  }, [loadMissionControl]);

  const engineers = useMemo(() => {
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
  }, [data.metrics, data.workspace.organizations]);

  const sprintCards = useMemo(() => {
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
  }, [data.automationMissions]);

  const artifacts = useMemo(() => {
    const roadmap = data.product.roadmap || [];
    const opportunities = data.product.opportunities || [];
    return [
      ['Repository', data.workspace.repositories?.[0]?.status || 'Connected', data.workspace.repositories?.[0]?.name || 'Active workspace'],
      ['Product Roadmap', roadmap.length ? `${roadmap.length} items` : 'Pending', roadmap[0]?.release_candidate || 'Generate product mission'],
      ['Opportunities', opportunities.length ? `${opportunities.length} ranked` : 'Pending', opportunities[0]?.title || 'No ranked opportunity'],
      ['Runtime Events', `${data.events.length} recent`, data.events[0]?.event_type || 'Waiting for mission activity'],
      ['Checkpoints', pct(data.metrics.checkpoint_frequency, 0.35), 'Evidence captured per task'],
      ['Recovery', pct(data.metrics.recovery_success, 0.95), 'Runtime replay confidence'],
    ];
  }, [data]);

  const controls = useMemo(() => [
    ['Approval Queue', data.dashboard.notifications?.length ? `${data.dashboard.notifications.length} waiting` : '0 waiting', 'Review important decisions'],
    ['Automation Missions', `${data.automationMissions.length}`, 'Persisted from triggers and workflows'],
    ['Product Health', data.product.product_health || 'unknown', 'Product intelligence dashboard'],
    ['Worker Utilization', pct(data.metrics.worker_utilization, 0.25), 'Runtime kernel activity'],
    ['Retry Rate', pct(data.metrics.retry_rate, 0.05), 'Durable execution reliability'],
    ['Lease Expirations', String(data.metrics.lease_expirations || 0), 'Recovery worker signal'],
  ], [data]);

  const activity = data.events.length
    ? data.events.map((event) => [eventTime(event), eventTitle(event)])
    : [
        ['09:21', 'Runtime kernel is ready for durable missions.'],
        ['09:24', 'Automation, product, and experience APIs are connected.'],
        ['09:27', 'Create a mission to start the live feed.'],
      ];

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
              <button type="button" onClick={createAutomationMission} disabled={!!busyAction}><Rocket size={16} /> {busyAction === 'automation' ? 'Creating...' : 'Launch Automation'}</button>
            </div>
          </header>
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
