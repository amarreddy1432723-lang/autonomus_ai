'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, BriefcaseBusiness, CheckCircle2, CreditCard, RefreshCw, Rocket, ShieldAlert, Users } from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from './admin.module.css';

type Summary = {
  users: number;
  active_subscriptions: number;
  usage_events: number;
  total_tokens: number;
  estimated_cost_usd: number;
  error_rate: number;
  audit_events: number;
  jobs: { queued: number; running: number; failed: number; total: number };
  plans: Array<{ plan: string; status: string; count: number }>;
};

type AdminUser = {
  id: string;
  email: string;
  name?: string | null;
  auth_provider?: string | null;
  is_active: boolean;
  created_at?: string | null;
  subscription: { plan: string; status: string; provider?: string | null };
  usage: { events: number; tokens: number; cost: number };
  jobs: { jobs: number; failed: number };
};

type Usage = {
  usage_events: number;
  total_tokens: number;
  routes: Array<{ route: string; events: number; tokens: number; cost: number }>;
};

type Job = {
  id: string;
  user_id: string;
  mode: string;
  status: string;
  approval_state?: string | null;
  created_at?: string | null;
};

type Health = {
  database: { ok: boolean; error?: string | null };
  redis: { configured: boolean; ok: boolean; queue_depth?: number | null; error?: string | null };
  workers: { queue_depth?: number | null; stale_jobs: number; configured_mode: string };
  checked_at: string;
};

type AbuseFlag = {
  user_id: string;
  email?: string | null;
  reasons: string[];
  events_24h: number;
  tokens_24h: number;
  cost_24h: number;
  failed_jobs_24h: number;
};

type ReadinessCheck = {
  name: string;
  ok: boolean;
  detail: string;
  severity: 'ok' | 'warning' | 'blocker';
  action?: string;
};

type ReleaseReadiness = {
  ready: boolean;
  environment: string;
  release: string;
  blockers: ReadinessCheck[];
  warnings: ReadinessCheck[];
  checks: ReadinessCheck[];
  summary?: { blockers: number; warnings: number; checks: number };
  runbook?: {
    recommended_next_step?: string;
    verify_command?: string;
    smoke_command?: string;
    deploy_command?: string;
    backup_command?: string;
    restore_command?: string;
    rollback_command?: string;
    operations_doc?: string;
    release_notes?: string;
    sequence?: string[];
  };
  checked_at: string;
};

type BillingHealth = {
  ready: boolean;
  stripe_secret_configured: boolean;
  webhook_secret_configured: boolean;
  stripe_sdk_available: boolean;
  missing_prices: string[];
  blockers: string[];
  warnings: string[];
};

type ObservabilityHealth = {
  ready: boolean;
  release: string;
  environment: string;
  metrics_endpoint?: string | null;
  logging: {
    format: string;
    request_id_header: string;
    trace_id_header: string;
    response_time_header: string;
  };
  checks: ReadinessCheck[];
  warnings: ReadinessCheck[];
  checked_at: string;
};

type AuditLog = {
  id: number | string;
  user_id: string;
  session_id?: string | null;
  event_type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  actor_type?: string | null;
  actor_id?: string | null;
  action: string;
  old_value?: unknown;
  new_value?: unknown;
  metadata?: Record<string, unknown>;
  occurred_at?: string | null;
};

const money = (value?: number) => `$${Number(value || 0).toFixed(4)}`;
const compact = (value?: number) => Intl.NumberFormat('en', { notation: 'compact' }).format(Number(value || 0));

async function safeAdminRequest(path: string, fallback: any) {
  try {
    return await apiRequest(path);
  } catch (error) {
    return {
      ...fallback,
      unavailable: true,
      unavailable_reason: error instanceof Error ? error.message : 'Endpoint unavailable',
    };
  }
}

function StatusPill({ value }: { value: string }) {
  const lowered = value.toLowerCase();
  const className = lowered.includes('active') || lowered.includes('ok') || lowered.includes('completed')
    ? `${styles.pill} ${styles.pillOk}`
    : lowered.includes('failed') || lowered.includes('dead') || lowered.includes('error')
      ? `${styles.pill} ${styles.pillBad}`
      : `${styles.pill} ${styles.pillWarn}`;
  return <span className={className}>{value}</span>;
}

export default function AdminPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [flags, setFlags] = useState<AbuseFlag[]>([]);
  const [readiness, setReadiness] = useState<ReleaseReadiness | null>(null);
  const [billingHealth, setBillingHealth] = useState<BillingHealth | null>(null);
  const [observabilityHealth, setObservabilityHealth] = useState<ObservabilityHealth | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [selectedAuditLog, setSelectedAuditLog] = useState<AuditLog | null>(null);
  const [auditFilters, setAuditFilters] = useState({ user: '', eventType: '', entityType: '', action: '' });
  const [killingJobId, setKillingJobId] = useState('');
  const [retryingJobId, setRetryingJobId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadAdmin = async () => {
    setLoading(true);
    setError('');
    try {
      const [summaryData, usersData, usageData, jobsData, healthData, flagsData, readinessData, billingHealthData, observabilityData, auditData] = await Promise.all([
        safeAdminRequest('/api/v1/admin/summary', { users: 0, active_subscriptions: 0, usage_events: 0, total_tokens: 0, estimated_cost_usd: 0, error_rate: 0, audit_events: 0, jobs: { queued: 0, running: 0, failed: 0, total: 0 }, plans: [] }),
        safeAdminRequest('/api/v1/admin/users', { users: [] }),
        safeAdminRequest('/api/v1/admin/usage', { usage_events: 0, total_tokens: 0, routes: [] }),
        safeAdminRequest('/api/v1/admin/jobs', { jobs: [] }),
        safeAdminRequest('/api/v1/admin/system-health', { database: { ok: false, error: 'Not checked' }, redis: { configured: false, ok: false }, workers: { stale_jobs: 0, configured_mode: 'unknown' }, checked_at: '' }),
        safeAdminRequest('/api/v1/admin/abuse-flags', { flags: [] }),
        safeAdminRequest('/api/v1/admin/release-readiness', { ready: false, environment: 'unknown', release: 'backend route unavailable', blockers: [], warnings: [], checks: [], checked_at: '' }),
        safeAdminRequest('/api/v1/admin/billing-health', { ready: false, stripe_secret_configured: false, webhook_secret_configured: false, stripe_sdk_available: false, missing_prices: [], blockers: [], warnings: [] }),
        safeAdminRequest('/api/v1/admin/observability-health', { ready: false, release: 'local', environment: 'unknown', metrics_endpoint: null, logging: { format: 'json', request_id_header: 'X-Request-Id', trace_id_header: 'X-Trace-Id', response_time_header: 'X-Response-Time-Ms' }, checks: [], warnings: [], checked_at: '' }),
        safeAdminRequest(
          `/api/v1/admin/audit-logs?limit=25${auditFilters.user ? `&audit_user_id=${encodeURIComponent(auditFilters.user)}` : ''}${auditFilters.eventType ? `&event_type=${encodeURIComponent(auditFilters.eventType)}` : ''}${auditFilters.entityType ? `&entity_type=${encodeURIComponent(auditFilters.entityType)}` : ''}${auditFilters.action ? `&action=${encodeURIComponent(auditFilters.action)}` : ''}`,
          { audit_logs: [] }
        ),
      ]);
      setSummary(summaryData);
      setUsers(usersData.users || []);
      setUsage(usageData);
      setJobs(jobsData.jobs || []);
      setHealth(healthData);
      setFlags(flagsData.flags || []);
      setReadiness(readinessData);
      setBillingHealth(billingHealthData);
      setObservabilityHealth(observabilityData);
      setAuditLogs(auditData.audit_logs || []);
      const unavailable = [summaryData, usersData, usageData, jobsData, healthData, flagsData, readinessData, billingHealthData, observabilityData, auditData]
        .filter((item) => item?.unavailable)
        .map((item) => item.unavailable_reason);
      if (unavailable.length) {
        setError(`Some admin endpoints are unavailable. Restart agent-service to load the latest backend routes. First issue: ${unavailable[0]}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load admin dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAdmin();
  }, []);

  const killJob = async (jobId: string) => {
    setKillingJobId(jobId);
    setError('');
    try {
      await apiRequest(`/api/v1/admin/jobs/${jobId}/kill`, { method: 'POST' });
      await loadAdmin();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to kill job');
    } finally {
      setKillingJobId('');
    }
  };

  const retryJob = async (jobId: string) => {
    setRetryingJobId(jobId);
    setError('');
    try {
      await apiRequest(`/api/v1/admin/jobs/${jobId}/retry`, { method: 'POST' });
      await loadAdmin();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to retry job');
    } finally {
      setRetryingJobId('');
    }
  };

  const loadAuditDetail = async (auditId: number | string) => {
    setError('');
    try {
      const result = await apiRequest(`/api/v1/admin/audit-logs/${auditId}`);
      setSelectedAuditLog(result.audit_log || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load audit detail');
    }
  };

  const maxRouteEvents = useMemo(() => Math.max(...(usage?.routes || []).map((row) => row.events), 1), [usage]);

  return (
    <AppShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Arceus Operations</p>
            <h1 className={styles.title}>Admin, Billing & Abuse Defense</h1>
            <p className={styles.subtitle}>
              Monitor users, plan mix, usage spend, active jobs, abuse signals, and infrastructure health before expensive actions become incidents.
            </p>
          </div>
          <button className={styles.button} type="button" onClick={loadAdmin} disabled={loading}>
            <RefreshCw size={14} />
            {loading ? 'Refreshing' : 'Refresh'}
          </button>
        </header>

        {error && <div className={styles.error}>{error}</div>}

        <section className={styles.grid}>
          <div className={styles.card}>
            <span><Users size={13} /> Users</span>
            <strong>{compact(summary?.users)}</strong>
            <em>{compact(summary?.active_subscriptions)} active subscriptions</em>
          </div>
          <div className={styles.card}>
            <span><CreditCard size={13} /> Usage spend</span>
            <strong>{money(summary?.estimated_cost_usd)}</strong>
            <em>{compact(summary?.total_tokens)} tokens across {compact(summary?.usage_events)} events</em>
          </div>
          <div className={styles.card}>
            <span><BriefcaseBusiness size={13} /> Jobs</span>
            <strong>{compact(summary?.jobs?.total)}</strong>
            <em>{summary?.jobs?.running || 0} running, {summary?.jobs?.failed || 0} failed</em>
          </div>
          <div className={styles.card}>
            <span><ShieldAlert size={13} /> Abuse flags</span>
            <strong>{flags.length}</strong>
            <em>{summary?.error_rate || 0}% job error rate</em>
          </div>
          <div className={styles.card}>
            <span><Rocket size={13} /> Release readiness</span>
            <strong>{readiness?.ready ? 'Ready' : `${readiness?.blockers?.length || 0} blockers`}</strong>
            <em>{readiness?.warnings?.length || 0} warnings · {readiness?.release || 'local'}</em>
          </div>
          <div className={styles.card}>
            <span><Activity size={13} /> Observability</span>
            <strong>{observabilityHealth?.ready ? 'Ready' : `${observabilityHealth?.warnings?.length || 0} warnings`}</strong>
            <em>{observabilityHealth?.metrics_endpoint || 'metrics disabled'} · {observabilityHealth?.release || 'local'}</em>
          </div>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.stack}>
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Users & Plans</h2>
                <span>Latest 100 users</span>
              </div>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Plan</th>
                    <th>Usage</th>
                    <th>Jobs</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <strong>{user.email}</strong>
                        <div className={styles.muted}>{user.name || user.auth_provider || user.id.slice(0, 8)}</div>
                      </td>
                      <td>
                        <StatusPill value={`${user.subscription.plan} ${user.subscription.status}`} />
                        <div className={styles.muted}>{user.subscription.provider || 'internal'}</div>
                      </td>
                      <td>
                        {compact(user.usage.tokens)} tokens
                        <div className={styles.muted}>{user.usage.events} events · {money(user.usage.cost)}</div>
                      </td>
                      <td>
                        {user.jobs.jobs} total
                        <div className={user.jobs.failed ? styles.pillBad : styles.muted}>{user.jobs.failed} failed</div>
                      </td>
                    </tr>
                  ))}
                  {!users.length && (
                    <tr><td colSpan={4} className={styles.muted}>No users visible for this admin account.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Route Usage & Spend</h2>
                <span>Most active metered endpoints</span>
              </div>
              <div className={styles.bars}>
                {(usage?.routes || []).map((route) => (
                  <div className={styles.barRow} key={route.route}>
                    <span title={route.route}>{route.route.replace('/api/v1/', '')}</span>
                    <div className={styles.bar}><span style={{ width: `${Math.max(4, Math.round(route.events / maxRouteEvents * 100))}%` }} /></div>
                    <strong>{route.events}</strong>
                  </div>
                ))}
                {!usage?.routes?.length && <span className={styles.muted}>No usage events recorded yet.</span>}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Audit Trail</h2>
                <span>Latest 25 events</span>
              </div>
              <form
                className={styles.filterGrid}
                onSubmit={(event) => {
                  event.preventDefault();
                  loadAdmin();
                }}
              >
                <input value={auditFilters.user} onChange={(event) => setAuditFilters((current) => ({ ...current, user: event.target.value }))} placeholder="User UUID" />
                <input value={auditFilters.eventType} onChange={(event) => setAuditFilters((current) => ({ ...current, eventType: event.target.value }))} placeholder="Event type" />
                <input value={auditFilters.entityType} onChange={(event) => setAuditFilters((current) => ({ ...current, entityType: event.target.value }))} placeholder="Entity type" />
                <input value={auditFilters.action} onChange={(event) => setAuditFilters((current) => ({ ...current, action: event.target.value }))} placeholder="Action contains" />
                <button type="submit">Filter</button>
                <button type="button" onClick={() => { setAuditFilters({ user: '', eventType: '', entityType: '', action: '' }); setTimeout(loadAdmin, 0); }}>Clear</button>
              </form>
              <div className={styles.list}>
                {auditLogs.map((log) => (
                  <button className={`${styles.row} ${styles.auditRowButton}`} type="button" key={log.id} onClick={() => loadAuditDetail(log.id)}>
                    <div>
                      <strong>{log.event_type}</strong>
                      <small>{log.action} · {log.entity_type || 'system'}</small>
                    </div>
                    <span className={styles.muted}>{log.occurred_at ? new Date(log.occurred_at).toLocaleTimeString() : ''}</span>
                  </button>
                ))}
                {!auditLogs.length && <span className={styles.muted}>No audit logs recorded yet.</span>}
              </div>
              {selectedAuditLog && (
                <div className={styles.detailBox}>
                  <div className={styles.panelHeader}>
                    <h3>{selectedAuditLog.event_type}</h3>
                    <button type="button" onClick={() => setSelectedAuditLog(null)}>Close</button>
                  </div>
                  <small>{selectedAuditLog.action}</small>
                  <code>User: {selectedAuditLog.user_id}</code>
                  {selectedAuditLog.entity_type && <code>Entity: {selectedAuditLog.entity_type} {selectedAuditLog.entity_id || ''}</code>}
                  <pre>{JSON.stringify({
                    actor: `${selectedAuditLog.actor_type || 'unknown'}:${selectedAuditLog.actor_id || ''}`,
                    old_value: selectedAuditLog.old_value,
                    new_value: selectedAuditLog.new_value,
                    metadata: selectedAuditLog.metadata,
                  }, null, 2)}</pre>
                </div>
              )}
            </div>
          </div>

          <div className={styles.stack}>
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Release Gate</h2>
                <span>{readiness?.runbook?.recommended_next_step || readiness?.environment || 'unknown'}</span>
              </div>
              {readiness?.runbook && (
                <div className={styles.runbookBox}>
                  <strong>{readiness.ready ? 'Ready for staged deploy' : 'Release blocked'}</strong>
                  <small>{readiness.summary?.blockers || 0} blockers · {readiness.summary?.warnings || 0} warnings · {readiness.release || 'local'}</small>
                  <code>{readiness.runbook.verify_command}</code>
                  <code>{readiness.ready ? readiness.runbook.deploy_command : readiness.runbook.smoke_command}</code>
                </div>
              )}
              <div className={styles.list}>
                {(readiness?.checks || []).map((check) => (
                  <div className={styles.readinessRow} data-severity={check.ok ? 'ok' : check.severity} key={check.name}>
                    <div>
                      <strong>{check.name}</strong>
                      <small>{check.detail}</small>
                      {!check.ok && check.action && <small className={styles.actionHint}>{check.action}</small>}
                    </div>
                    {check.ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                  </div>
                ))}
              </div>
              {readiness?.runbook?.sequence?.length ? (
                <div className={styles.runbookSteps}>
                  {readiness.runbook.sequence.map((step, index) => (
                    <span key={`${step}-${index}`}>{index + 1}. {step}</span>
                  ))}
                </div>
              ) : null}
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Billing Gate</h2>
                <span>{billingHealth?.ready ? 'ready' : 'needs setup'}</span>
              </div>
              <div className={styles.list}>
                <div className={styles.row}>
                  <div><strong>Stripe secret</strong><small>Checkout API access</small></div>
                  <StatusPill value={billingHealth?.stripe_secret_configured ? 'ok' : 'missing'} />
                </div>
                <div className={styles.row}>
                  <div><strong>Webhook secret</strong><small>Verified subscription sync</small></div>
                  <StatusPill value={billingHealth?.webhook_secret_configured ? 'ok' : 'missing'} />
                </div>
                <div className={styles.row}>
                  <div><strong>Stripe SDK</strong><small>Python package availability</small></div>
                  <StatusPill value={billingHealth?.stripe_sdk_available ? 'ok' : 'missing'} />
                </div>
                {!!billingHealth?.missing_prices?.length && (
                  <div className={styles.notice}>
                    Missing prices: {billingHealth.missing_prices.join(', ')}
                  </div>
                )}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Observability Gate</h2>
                <span>{observabilityHealth?.ready ? 'ready' : 'needs setup'}</span>
              </div>
              <div className={styles.list}>
                {(observabilityHealth?.checks || []).map((check) => (
                  <div className={styles.readinessRow} data-severity={check.ok ? 'ok' : check.severity} key={check.name}>
                    <div>
                      <strong>{check.name}</strong>
                      <small>{check.detail}</small>
                    </div>
                    {check.ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                  </div>
                ))}
                <div className={styles.notice}>
                  Logs include {observabilityHealth?.logging?.request_id_header || 'X-Request-Id'}, {observabilityHealth?.logging?.trace_id_header || 'X-Trace-Id'}, and response time headers for incident tracing.
                </div>
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>System Health</h2>
                <span>{health?.checked_at ? new Date(health.checked_at).toLocaleTimeString() : 'not checked'}</span>
              </div>
              <div className={styles.list}>
                <div className={styles.row}>
                  <div><strong>Database</strong><small>{health?.database?.error || 'SQL connectivity'}</small></div>
                  <StatusPill value={health?.database?.ok ? 'ok' : 'error'} />
                </div>
                <div className={styles.row}>
                  <div><strong>Redis</strong><small>{health?.redis?.configured ? `queue depth ${health.redis.queue_depth ?? 'unknown'}` : 'not configured'}</small></div>
                  <StatusPill value={health?.redis?.ok ? 'ok' : health?.redis?.configured ? 'error' : 'dev fallback'} />
                </div>
                <div className={styles.row}>
                  <div><strong>Workers</strong><small>{health?.workers?.configured_mode || 'unknown'}</small></div>
                  <StatusPill value={(health?.workers?.stale_jobs || 0) > 0 ? 'stale jobs' : 'ok'} />
                </div>
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Plan Breakdown</h2>
                <span>Subscriptions</span>
              </div>
              <div className={styles.list}>
                {(summary?.plans || []).map((plan) => (
                  <div className={styles.row} key={`${plan.plan}-${plan.status}`}>
                    <div><strong>{plan.plan}</strong><small>{plan.status}</small></div>
                    <span className={styles.pill}>{plan.count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Abuse Signals</h2>
                <span>24h heuristic flags</span>
              </div>
              <div className={styles.list}>
                {flags.map((flag) => (
                  <div className={styles.row} key={flag.user_id}>
                    <div>
                      <strong>{flag.email || flag.user_id.slice(0, 8)}</strong>
                      <small>{flag.reasons.join(', ')}</small>
                    </div>
                    <AlertTriangle size={14} color="#f59e0b" />
                  </div>
                ))}
                {!flags.length && <span className={styles.muted}>No abuse flags in the last 24 hours.</span>}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Active Jobs</h2>
                <span>Latest 100</span>
              </div>
              <div className={styles.list}>
                {jobs.slice(0, 12).map((job) => (
                  <div className={styles.row} key={job.id}>
                    <div><strong>{job.mode}</strong><small>{job.id.slice(0, 8)} · {job.approval_state || 'none'}</small></div>
                    <div className={styles.jobActions}>
                      <StatusPill value={job.status} />
                      {!['completed', 'failed', 'cancelled', 'dead_letter', 'timeout'].includes(job.status) && (
                        <button className={styles.killButton} type="button" onClick={() => killJob(job.id)} disabled={killingJobId === job.id}>
                          {killingJobId === job.id ? 'Killing' : 'Kill'}
                        </button>
                      )}
                      {['failed', 'dead_letter', 'timeout', 'cancelled'].includes(job.status) && job.mode.startsWith('background_') && (
                        <button className={styles.retryButton} type="button" onClick={() => retryJob(job.id)} disabled={retryingJobId === job.id}>
                          {retryingJobId === job.id ? 'Retrying' : 'Retry'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {!jobs.length && <span className={styles.muted}>No jobs yet.</span>}
              </div>
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
