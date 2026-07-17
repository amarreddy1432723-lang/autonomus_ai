'use client';

import Link from 'next/link';
import React, { useEffect, useState } from 'react';
import AppShell from '../../components/AppShell';
import ServiceRecoveryBanner from '../../components/ServiceRecoveryBanner';
import { AlertTriangle, Bell, CheckCircle2, Code2, Cpu, CreditCard, Play, RefreshCw, Shield, User } from 'lucide-react';
import { apiRequest } from '../../utils/api';
import { probeServiceHealth, serviceHealthCopy, type ServiceHealthSnapshot } from '../../utils/serviceHealth';
import { deriveVaultKey, generateSaltHex, getVaultKey, setVaultKey, clearVaultKey } from '../../utils/vault';

type AutonomyLevel = 'observer' | 'assistant' | 'partner' | 'chief_of_staff';

type AutonomyStatus = {
  autonomy_level: AutonomyLevel;
  model_confidence: number;
  queued_tasks: number;
  waiting_approval_tasks: number;
  pending_approvals: number;
  task_executions: number;
  thresholds: {
    auto: number;
    notify: number;
    confirm: number;
  };
  guardrails: {
    approval_timeout_minutes: number;
    safe_default: string;
  };
};

type BillingSummary = {
  plan: {
    key: string;
    name: string;
    status: string;
    billing_cycle: string;
    monthly_usd: number;
    monthly_inr: number;
    current_period_end?: string | null;
    models: string[];
  };
  usage: Array<{
    metric: string;
    label: string;
    period: string;
    used: number;
    limit: number | null;
    remaining: number | null;
    percent: number;
    locked: boolean;
  }>;
  stripe: {
    configured: boolean;
    customer_id?: string | null;
    subscription_id?: string | null;
  };
  plans: Record<string, any>;
};

type CodeProject = {
  id: string;
  name: string;
  description?: string;
  repo_url?: string;
  status?: string;
  file_ids?: string[];
  active_session_id?: string | null;
  last_opened_at?: string | null;
};

type LocalModelStatus = {
  provider: string;
  runtime: string;
  running: boolean;
  base_url: string;
  active_model: string;
  available_models: string[];
  models: Array<{ name: string; size?: number; family?: string; parameter_size?: string; quantization_level?: string }>;
  requires_api_key: boolean;
  supports_offline: boolean;
  error?: string | null;
  setup?: { download_url: string; recommended_pull: string };
  preferences?: ModelPreferences;
};

type ModelPreferences = {
  mode: 'arceus_local' | 'arceus_cloud' | 'provider';
  provider: string;
  model: string;
  allow_cloud_fallback: boolean;
  confirm_before_cloud_transfer: boolean;
};

type ModelAccessSummary = {
  plan: string;
  providers: Array<{
    provider: string;
    label: string;
    managed_configured: boolean;
    byok_supported: boolean;
    byok_connected: boolean;
    privacy: { mode?: string; supports_offline?: boolean };
    recommended_use: string[];
  }>;
};

const autonomyOptions: { value: AutonomyLevel; label: string }[] = [
  { value: 'observer', label: 'Observer' },
  { value: 'assistant', label: 'Assistant' },
  { value: 'partner', label: 'Partner' },
  { value: 'chief_of_staff', label: 'Chief of staff' },
];

type SettingsTab = 'autonomy' | 'billing' | 'profile' | 'notifications' | 'training' | 'vault' | 'code' | 'models';

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('code');
  const [isElectron, setIsElectron] = useState(false);
  const [serviceHealth, setServiceHealth] = useState<ServiceHealthSnapshot>(() => {
    const copy = serviceHealthCopy('auth_required');
    return { state: 'auth_required', label: copy.label, detail: copy.detail, online: false, authReady: false, checkedAt: '' };
  });
  const [githubConnected, setGithubConnected] = useState(true);
  const [autonomyStatus, setAutonomyStatus] = useState<AutonomyStatus | null>(null);
  const [dryRunResult, setDryRunResult] = useState<string>('');
  const [loadingAutonomy, setLoadingAutonomy] = useState(true);
  const [autonomyError, setAutonomyError] = useState('');

  // Self-training States
  const [trainingJobs, setTrainingJobs] = useState<any[]>([]);
  const [activeFinetunedModel, setActiveFinetunedModel] = useState<string>('None');
  const [isTrainingInFlight, setIsTrainingInFlight] = useState(false);
  const [trainingError, setTrainingError] = useState('');
  const [billingSummary, setBillingSummary] = useState<BillingSummary | null>(null);
  const [billingMessage, setBillingMessage] = useState('');
  const [codeProjects, setCodeProjects] = useState<CodeProject[]>([]);
  const [codeProjectsLoading, setCodeProjectsLoading] = useState(false);
  const [codeProjectsError, setCodeProjectsError] = useState('');
  const [localModelStatus, setLocalModelStatus] = useState<LocalModelStatus | null>(null);
  const [modelAccess, setModelAccess] = useState<ModelAccessSummary | null>(null);
  const [modelPreferences, setModelPreferences] = useState<ModelPreferences>({ mode: 'arceus_local', provider: 'ollama', model: 'qwen2.5-coder:7b', allow_cloud_fallback: false, confirm_before_cloud_transfer: true });
  const [modelMessage, setModelMessage] = useState('');
  const [modelTestPrompt, setModelTestPrompt] = useState('Reply with OK and your model name.');
  const [modelTestResponse, setModelTestResponse] = useState('');

  const loadAutonomyStatus = async () => {
    setLoadingAutonomy(true);
    setAutonomyError('');
    try {
      const data = await apiRequest('/api/v1/agents/autonomy/status');
      setAutonomyStatus(data);
    } catch (error) {
      setAutonomyError(error instanceof Error ? error.message : 'Unable to load autonomy policy');
    } finally {
      setLoadingAutonomy(false);
    }
  };

  const loadTrainingData = async () => {
    try {
      const activeModelData = await apiRequest('/api/v1/training/active-model');
      setActiveFinetunedModel(activeModelData.active_finetuned_model);
      const jobsData = await apiRequest('/api/v1/training/jobs');
      setTrainingJobs(jobsData);
    } catch (err) {
      console.error('Error loading training details:', err);
    }
  };

  const loadBillingSummary = async () => {
    try {
      const data = await apiRequest('/api/v1/billing/summary');
      setBillingSummary(data);
    } catch (error) {
      setBillingMessage(error instanceof Error ? error.message : 'Unable to load billing summary');
    }
  };

  const loadCodeProjects = async () => {
    setCodeProjectsLoading(true);
    setCodeProjectsError('');
    try {
      const data = await apiRequest('/api/v1/code/projects');
      setCodeProjects(data || []);
    } catch (error) {
      setCodeProjectsError(error instanceof Error ? error.message : 'Unable to load Arceus Code projects');
    } finally {
      setCodeProjectsLoading(false);
    }
  };

  const refreshServiceHealth = async () => {
    if (typeof window === 'undefined') return;
    const snapshot = await probeServiceHealth();
    setServiceHealth(snapshot);
  };

  const loadModelSettings = async () => {
    setModelMessage('');
    try {
      const [localStatus, accessSummary, preferences] = await Promise.all([
        apiRequest('/api/v1/models/local/status'),
        apiRequest('/api/v1/models/access'),
        apiRequest('/api/v1/models/preferences'),
      ]);
      setLocalModelStatus(localStatus);
      setModelAccess(accessSummary);
      setModelPreferences(preferences);
    } catch (error) {
      setModelMessage(error instanceof Error ? error.message : 'Unable to load model settings');
    }
  };

  const saveModelPreferences = async () => {
    setModelMessage('');
    try {
      const updated = await apiRequest('/api/v1/models/preferences', {
        method: 'PATCH',
        body: JSON.stringify(modelPreferences),
      });
      setModelPreferences(updated);
      setModelMessage('Model preferences saved.');
      await loadModelSettings();
    } catch (error) {
      setModelMessage(error instanceof Error ? error.message : 'Unable to save model preferences');
    }
  };

  const testLocalModel = async () => {
    setModelMessage('');
    setModelTestResponse('');
    try {
      const result = await apiRequest('/api/v1/models/local/test', {
        method: 'POST',
        body: JSON.stringify({ prompt: modelTestPrompt, model: modelPreferences.model }),
      });
      if (result.ok) {
        setModelTestResponse(result.response || 'Model responded successfully.');
      } else {
        setModelMessage(result.hint || result.error || 'Local model test failed.');
      }
    } catch (error) {
      setModelMessage(error instanceof Error ? error.message : 'Unable to test local model');
    }
  };

  const renameCodeProject = async (project: CodeProject) => {
    setCodeProjectsError(`Rename "${project.name}" from the project menu. Native browser prompts are disabled in Arceus.`);
  };

  const archiveCodeProject = async (project: CodeProject) => {
    if (!window.confirm(`Archive "${project.name}"?`)) return;
    setCodeProjectsError('');
    try {
      await apiRequest(`/api/v1/code/projects/${project.id}`, { method: 'DELETE' });
      await loadCodeProjects();
    } catch (error) {
      setCodeProjectsError(error instanceof Error ? error.message : 'Unable to archive project');
    }
  };


  const triggerSelfTraining = async () => {
    setIsTrainingInFlight(true);
    setTrainingError('');
    try {
      const newJob = await apiRequest('/api/v1/training/train', { method: 'POST' });
      alert(`Fine-tuning job ${newJob.job_id} successfully triggered on OpenAI!`);
      await loadTrainingData();
    } catch (err) {
      setTrainingError(err instanceof Error ? err.message : 'Failed to trigger training job.');
    } finally {
      setIsTrainingInFlight(false);
    }
  };

  useEffect(() => {
    const desktop = typeof window !== 'undefined' && Boolean((window as any).electron);
    setIsElectron(desktop);
    void refreshServiceHealth();
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('tab') === 'billing') {
        setActiveTab('billing');
      } else if (params.get('tab') === 'models') {
        setActiveTab('models');
      } else if (desktop) {
        setActiveTab('code');
      }
      if (params.get('checkout') === 'success') {
        setBillingMessage('Checkout completed. Your subscription will update after Stripe confirms the webhook.');
      } else if (params.get('checkout') === 'cancelled') {
        setBillingMessage('Checkout cancelled. Your current plan is unchanged.');
      }
    }
    if (!desktop) {
      loadAutonomyStatus();
      loadTrainingData();
      loadBillingSummary();
    } else {
      setLoadingAutonomy(false);
    }
    loadCodeProjects();
    loadModelSettings();
  }, []);

  const startCheckout = async (plan: string) => {
    setBillingMessage('');
    try {
      const data = await apiRequest('/api/v1/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ plan, billing_cycle: 'monthly' }),
      });
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      setBillingMessage(data.message || 'Checkout is ready.');
    } catch (error) {
      setBillingMessage(error instanceof Error ? error.message : 'Checkout failed');
    }
  };

  const openBillingPortal = async () => {
    setBillingMessage('');
    try {
      const data = await apiRequest('/api/v1/billing/portal', { method: 'POST' });
      if (data.portal_url) {
        window.location.href = data.portal_url;
        return;
      }
      setBillingMessage(data.message || 'Billing portal is not ready for this account yet.');
    } catch (error) {
      setBillingMessage(error instanceof Error ? error.message : 'Billing portal failed');
    }
  };

  const updateAutonomyLevel = async (autonomy_level: AutonomyLevel) => {
    setAutonomyError('');
    try {
      const data = await apiRequest('/api/v1/agents/autonomy/level', {
        method: 'PATCH',
        body: JSON.stringify({ autonomy_level }),
      });
      setAutonomyStatus((current) => current ? { ...current, autonomy_level: data.autonomy_level } : current);
      await loadAutonomyStatus();
    } catch (error) {
      setAutonomyError(error instanceof Error ? error.message : 'Unable to update autonomy level');
    }
  };

  const runDryCheck = async () => {
    setAutonomyError('');
    setDryRunResult('');
    try {
      const data = await apiRequest('/api/v1/agents/autonomy/run', {
        method: 'POST',
        body: JSON.stringify({ max_tasks: 3, dry_run: true }),
      });
      setDryRunResult(`${data.evaluated} checked · ${data.executed} would execute · ${data.approval_required} need approval`);
    } catch (error) {
      setAutonomyError(error instanceof Error ? error.message : 'Unable to run autonomy check');
    }
  };

  const visibleTabs: Array<{ tab: SettingsTab; label: string; icon: React.ElementType }> = isElectron ? [
    { tab: 'code', label: 'Arceus Code', icon: Code2 },
    { tab: 'models', label: 'AI Models', icon: Cpu },
    { tab: 'vault', label: 'Privacy Vault', icon: Shield },
  ] : [
    { tab: 'autonomy', label: 'Autonomy policy', icon: Shield },
    { tab: 'billing', label: 'Usage & Billing', icon: CreditCard },
    { tab: 'profile', label: 'Profile settings', icon: User },
    { tab: 'notifications', label: 'Notifications', icon: Bell },
    { tab: 'training', label: 'Model Self-Training', icon: RefreshCw },
    { tab: 'models', label: 'AI Models', icon: Cpu },
    { tab: 'code', label: 'Arceus Code', icon: Code2 },
    { tab: 'vault', label: 'Privacy Vault', icon: Shield },
  ];

  const tabButtonStyle = (tab: SettingsTab) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: activeTab === tab ? 'var(--color-bg-hover)' : 'transparent',
    border: 'none',
    color: activeTab === tab ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
    padding: '8px 12px',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    textAlign: 'left' as const,
    width: '100%',
    fontSize: 'var(--text-sm)'
  });

  return (
    <AppShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: 0 }}>
          System Settings
        </h1>

        {isElectron && (
          <ServiceRecoveryBanner
            health={serviceHealth}
            onRetry={refreshServiceHealth}
          />
        )}

        <div style={{
          display: 'grid',
          gridTemplateColumns: '200px 1fr',
          gap: '32px',
          backgroundColor: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          padding: '24px'
        }}>
          {/* Settings Sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderRight: '1px solid var(--color-border)', paddingRight: '16px' }}>
            {visibleTabs.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.tab} style={tabButtonStyle(item.tab)} onClick={() => setActiveTab(item.tab)}>
                  <Icon size={14} /> {item.label}
                </button>
              );
            })}
          </div>

          {/* Settings Content Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {activeTab === 'billing' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 800 }}>Usage & Billing</h2>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                      Track plan limits, interview trials, usage, and Stripe readiness.
                    </span>
                  </div>
                  <button
                    onClick={loadBillingSummary}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                  >
                    <RefreshCw size={14} /> Refresh
                  </button>
                </div>

                {billingSummary && (
                  <>
                    <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div>
                        <span style={{ display: 'block', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>Current Plan</span>
                        <strong style={{ display: 'block', fontSize: '22px', marginTop: '4px' }}>{billingSummary.plan.name}</strong>
                        <span style={{ display: 'block', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)', marginTop: '4px' }}>
                          ${billingSummary.plan.monthly_usd}/mo · ₹{billingSummary.plan.monthly_inr}/mo · {billingSummary.plan.status}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <button onClick={openBillingPortal} style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                          Manage billing
                        </button>
                        <button onClick={() => startCheckout('starter')} style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                          Starter $12
                        </button>
                        <button onClick={() => startCheckout('pro')} style={{ background: 'var(--color-accent-primary)', border: '1px solid var(--color-accent-primary)', color: 'white', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 800 }}>
                          Upgrade Pro $29
                        </button>
                        <button onClick={() => startCheckout('enterprise')} style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                          Enterprise $79
                        </button>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                      {billingSummary.usage.map((item) => {
                        const unlimited = item.limit === null;
                        return (
                          <div key={item.metric} style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                              <strong style={{ fontSize: 'var(--text-sm)' }}>{item.label}</strong>
                              <span style={{ color: item.locked ? 'var(--color-error)' : 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                                {item.locked ? 'Locked' : unlimited ? `${item.used} / ∞` : `${item.used} / ${item.limit}`}
                              </span>
                            </div>
                            <div style={{ height: '7px', background: 'var(--color-bg-primary)', borderRadius: '999px', overflow: 'hidden', border: '1px solid var(--color-border)' }}>
                              <div style={{ width: unlimited ? '100%' : `${item.percent}%`, height: '100%', background: item.locked ? 'var(--color-error)' : item.percent > 85 ? 'var(--color-warning)' : 'var(--color-accent-primary)' }} />
                            </div>
                            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '10px' }}>{item.period} limit</span>
                          </div>
                        );
                      })}
                    </div>

                    <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '14px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <strong style={{ fontSize: 'var(--text-sm)' }}>Stripe Status</strong>
                      <span style={{ color: billingSummary.stripe.configured ? 'var(--color-success)' : 'var(--color-warning)', fontSize: 'var(--text-xs)' }}>
                        {billingSummary.stripe.configured ? 'Stripe secret key detected.' : 'Stripe is not configured yet. Add STRIPE_SECRET_KEY and price IDs to enable paid upgrades.'}
                      </span>
                      <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                        Models included: {billingSummary.plan.models.join(', ')}
                      </span>
                    </div>
                  </>
                )}

                {billingMessage && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-warning)' }}>
                    <AlertTriangle size={14} /> {billingMessage}
                  </span>
                )}
              </div>
            )}

            {activeTab === 'models' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 800 }}>AI Models</h2>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                      Choose local, managed cloud, or connected provider models. Local mode keeps code on this machine.
                    </span>
                  </div>
                  <button
                    onClick={loadModelSettings}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                  >
                    <RefreshCw size={14} /> Refresh
                  </button>
                </div>

                {modelMessage && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: modelMessage.includes('saved') ? 'var(--color-success)' : 'var(--color-warning)' }}>
                    <AlertTriangle size={14} /> {modelMessage}
                  </span>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                  {[
                    { id: 'arceus_local', title: 'Arceus Local', desc: 'Private, offline after model download, no API charges.' },
                    { id: 'arceus_cloud', title: 'Arceus Cloud', desc: 'Managed Arceus model access through subscription credits.' },
                    { id: 'provider', title: 'Connect Provider', desc: 'Use your own OpenAI, Anthropic, Google, Groq, or custom endpoint.' },
                  ].map((mode) => {
                    const active = modelPreferences.mode === mode.id;
                    return (
                      <button
                        key={mode.id}
                        type="button"
                        onClick={() => setModelPreferences((current) => ({ ...current, mode: mode.id as ModelPreferences['mode'], provider: mode.id === 'arceus_local' ? 'ollama' : mode.id === 'arceus_cloud' ? 'autonomus' : current.provider }))}
                        style={{ textAlign: 'left', background: active ? 'rgba(124, 108, 240, 0.12)' : 'var(--color-bg-tertiary)', border: `1px solid ${active ? 'var(--color-accent-primary)' : 'var(--color-border)'}`, color: 'var(--color-text-primary)', borderRadius: 'var(--radius-md)', padding: '14px', cursor: 'pointer' }}
                      >
                        <strong style={{ display: 'block', fontSize: 'var(--text-sm)' }}>{mode.title}</strong>
                        <span style={{ display: 'block', marginTop: '6px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)', lineHeight: 1.5 }}>{mode.desc}</span>
                      </button>
                    );
                  })}
                </div>

                <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'grid', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <div>
                      <strong style={{ display: 'block', fontSize: 'var(--text-sm)' }}>Local runtime</strong>
                      <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                        Ollama at {localModelStatus?.base_url || 'http://127.0.0.1:11434'}
                      </span>
                    </div>
                    <span style={{ color: localModelStatus?.running ? 'var(--color-success)' : 'var(--color-warning)', fontSize: 'var(--text-xs)', fontWeight: 800 }}>
                      {localModelStatus?.running ? 'Running' : 'Offline'}
                    </span>
                  </div>
                  {!localModelStatus?.running && (
                    <div style={{ border: '1px solid rgba(234, 179, 8, 0.35)', background: 'rgba(234, 179, 8, 0.08)', borderRadius: 'var(--radius-sm)', padding: '10px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                      Install Ollama, then run <code>{localModelStatus?.setup?.recommended_pull || 'ollama pull qwen2.5-coder:7b'}</code>.
                    </div>
                  )}
                  <label style={{ display: 'grid', gap: '6px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    Selected local model
                    <select
                      value={modelPreferences.model}
                      onChange={(event) => setModelPreferences((current) => ({ ...current, model: event.target.value }))}
                      style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', borderRadius: 'var(--radius-sm)', padding: '9px 10px' }}
                    >
                      {(localModelStatus?.available_models?.length ? localModelStatus.available_models : [modelPreferences.model || 'qwen2.5-coder:7b']).map((name) => (
                        <option value={name} key={name}>{name}</option>
                      ))}
                    </select>
                  </label>
                  {!!localModelStatus?.models?.length && (
                    <div style={{ display: 'grid', gap: '8px' }}>
                      {localModelStatus.models.slice(0, 6).map((model) => (
                        <div key={model.name} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '8px 10px', fontSize: 'var(--text-xs)' }}>
                          <strong>{model.name}</strong>
                          <span style={{ color: 'var(--color-text-secondary)' }}>{model.parameter_size || model.family || 'local'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'grid', gap: '12px' }}>
                  <strong style={{ fontSize: 'var(--text-sm)' }}>Privacy and fallback</strong>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    <input
                      type="checkbox"
                      checked={modelPreferences.allow_cloud_fallback}
                      onChange={(event) => setModelPreferences((current) => ({ ...current, allow_cloud_fallback: event.target.checked }))}
                    />
                    Allow cloud fallback when the local model cannot complete a task.
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    <input
                      type="checkbox"
                      checked={modelPreferences.confirm_before_cloud_transfer}
                      onChange={(event) => setModelPreferences((current) => ({ ...current, confirm_before_cloud_transfer: event.target.checked }))}
                    />
                    Ask before sending project context to any cloud provider.
                  </label>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button onClick={saveModelPreferences} style={{ background: 'var(--color-accent-primary)', border: '1px solid var(--color-accent-primary)', color: 'white', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 800 }}>
                      Save model preferences
                    </button>
                    <button onClick={testLocalModel} style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', padding: '9px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                      Test local model
                    </button>
                  </div>
                  <textarea
                    value={modelTestPrompt}
                    onChange={(event) => setModelTestPrompt(event.target.value)}
                    rows={2}
                    style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', borderRadius: 'var(--radius-sm)', padding: '10px', resize: 'vertical' }}
                  />
                  {modelTestResponse && (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '10px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>{modelTestResponse}</pre>
                  )}
                </div>

                <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'grid', gap: '8px' }}>
                  <strong style={{ fontSize: 'var(--text-sm)' }}>Provider access</strong>
                  {(modelAccess?.providers || []).slice(0, 8).map((provider) => (
                    <div key={provider.provider} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '8px 10px', fontSize: 'var(--text-xs)' }}>
                      <div>
                        <strong>{provider.label}</strong>
                        <span style={{ display: 'block', color: 'var(--color-text-secondary)' }}>{provider.recommended_use.slice(0, 2).join(' · ')}</span>
                      </div>
                      <span style={{ color: provider.managed_configured || provider.byok_connected ? 'var(--color-success)' : 'var(--color-text-secondary)', fontWeight: 800 }}>
                        {provider.byok_connected ? 'BYOK' : provider.managed_configured ? 'Ready' : provider.byok_supported ? 'Connect key' : 'Not configured'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'training' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center' }}>
                  <div>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Autonomus AI Self-Training Loop</h2>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                      Train your personal instance of Autonomus AI using approved chat responses and resume corrections.
                    </span>
                  </div>
                  <button
                    onClick={loadTrainingData}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                  >
                    <RefreshCw size={14} /> Sync Statuses
                  </button>
                </div>

                <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
                  <span style={{ display: 'block', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>Active Fine-Tuned Model</span>
                  <strong style={{ display: 'block', fontSize: 'var(--text-base)', marginTop: '4px', wordBreak: 'break-all', color: activeFinetunedModel !== 'None' ? 'var(--color-accent-primary)' : 'var(--color-text-primary)' }}>
                    {activeFinetunedModel}
                  </strong>
                  {activeFinetunedModel === 'None' && (
                    <span style={{ display: 'block', color: 'var(--color-text-secondary)', fontSize: '10px', marginTop: '4px' }}>
                      Using default base model fallback (Groq Llama-3.3 / OpenAI gpt-4o-mini). Train a model below to activate custom fine-tuning.
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>Trigger Self-Training Job</h3>
                  <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', margin: 0 }}>
                    Starts an OpenAI fine-tuning run (uses `gpt-4o-mini` as base). Requires at least 10 approved examples. 
                    Examples are gathered when you click \"Train Autonomus\" on chat answers.
                  </p>
                  <button
                    onClick={triggerSelfTraining}
                    disabled={isTrainingInFlight}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      background: 'var(--color-accent-primary)',
                      border: '1px solid ' + (isTrainingInFlight ? 'var(--color-border)' : 'var(--color-accent-primary)'),
                      color: 'white',
                      padding: '10px 16px',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                      fontSize: 'var(--text-xs)',
                      fontWeight: 700,
                      width: 'fit-content'
                    }}
                  >
                    {isTrainingInFlight ? 'Starting Fine-Tuning Job...' : 'Start OpenAI Fine-Tuning Run'}
                  </button>
                  {trainingError && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: '#ef4444' }}>
                      <AlertTriangle size={14} /> {trainingError}
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '8px' }}>
                  <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>Fine-Tuning Jobs History</h3>
                  <div style={{ overflowX: 'auto', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: 'var(--color-bg-tertiary)', borderBottom: '1px solid var(--color-border)' }}>
                          <th style={{ padding: '8px 12px' }}>Job ID</th>
                          <th style={{ padding: '8px 12px' }}>Status</th>
                          <th style={{ padding: '8px 12px' }}>Created At</th>
                          <th style={{ padding: '8px 12px' }}>Fine-Tuned Model</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trainingJobs.map((job) => (
                          <tr key={job.job_id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                            <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{job.job_id}</td>
                            <td style={{ padding: '8px 12px' }}>
                              <span style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '10px',
                                fontWeight: 600,
                                background: job.status === 'succeeded' ? 'rgba(34, 197, 94, 0.2)' : job.status === 'failed' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(234, 179, 8, 0.2)',
                                color: job.status === 'succeeded' ? '#22c55e' : job.status === 'failed' ? '#ef4444' : '#eab308'
                              }}>
                                {job.status}
                              </span>
                            </td>
                            <td style={{ padding: '8px 12px' }}>{new Date(job.created_at).toLocaleString()}</td>
                            <td style={{ padding: '8px 12px', fontFamily: 'monospace', wordBreak: 'break-all' }}>{job.fine_tuned_model || '—'}</td>
                          </tr>
                        ))}
                        {trainingJobs.length === 0 && (
                          <tr>
                            <td colSpan={4} style={{ padding: '16px', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                              No training jobs recorded yet.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'autonomy' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>AI Autonomy Level</h2>
                    {loadingAutonomy && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Loading current policy</span>}
                  </div>
                  <button
                    onClick={loadAutonomyStatus}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                  >
                    <RefreshCw size={14} /> Refresh
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '8px' }}>
                  {autonomyOptions.map((option) => {
                    const selected = autonomyStatus?.autonomy_level === option.value;
                    return (
                      <button
                        key={option.value}
                        onClick={() => updateAutonomyLevel(option.value)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minHeight: '40px',
                          background: selected ? 'var(--color-bg-hover)' : 'transparent',
                          border: selected ? '1px solid var(--color-accent-primary)' : '1px solid var(--color-border)',
                          color: selected ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                          borderRadius: 'var(--radius-sm)',
                          cursor: 'pointer',
                          fontSize: 'var(--text-xs)',
                          fontWeight: 700,
                          whiteSpace: 'normal',
                        }}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>

                {autonomyStatus && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px' }}>
                    {[
                      ['Queued', autonomyStatus.queued_tasks],
                      ['Approvals', autonomyStatus.pending_approvals],
                      ['Waiting', autonomyStatus.waiting_approval_tasks],
                      ['Executions', autonomyStatus.task_executions],
                    ].map(([label, value]) => (
                      <div key={label} style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '12px' }}>
                        <span style={{ display: 'block', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>{label}</span>
                        <strong style={{ display: 'block', fontSize: 'var(--text-xl)', marginTop: '4px' }}>{value}</strong>
                      </div>
                    ))}
                  </div>
                )}

                {autonomyStatus && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                      <CheckCircle2 size={16} />
                      <span>Auto {autonomyStatus.thresholds.auto} · Notify {autonomyStatus.thresholds.notify} · Confirm {autonomyStatus.thresholds.confirm} · Timeout {autonomyStatus.guardrails.approval_timeout_minutes}m</span>
                    </div>
                    <button
                      onClick={runDryCheck}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'var(--color-accent-primary)', border: '1px solid var(--color-accent-primary)', color: 'white', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                    >
                      <Play size={14} /> Dry run
                    </button>
                  </div>
                )}

                {dryRunResult && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>{dryRunResult}</span>}
                {autonomyError && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: '#ef4444' }}>
                    <AlertTriangle size={14} /> {autonomyError}
                  </span>
                )}
              </div>
            )}

            {activeTab === 'profile' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Profile Settings</h2>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>User: Amar · Locale: en · Timezone: Asia/Calcutta</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Profile editing is staged here; persistence will use the user profile API when that endpoint is added.</span>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Notifications</h2>
                <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                  <input type="checkbox" defaultChecked /> In-app approval alerts
                </label>
                <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                  <input type="checkbox" /> Daily planning digest
                </label>
              </div>
            )}

            {activeTab === 'vault' && (
              <VaultSection />
            )}

            {activeTab === 'code' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 800 }}>Arceus Code Projects</h2>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                      Manage workspace project records separately from PA and Interview. Files stay attached only to Code projects.
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      onClick={loadCodeProjects}
                      disabled={codeProjectsLoading}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
                    >
                      <RefreshCw size={14} /> Refresh
                    </button>
                    <Link
                      href="/workspace"
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'var(--color-accent-primary)', border: '1px solid var(--color-accent-primary)', color: 'white', padding: '8px 12px', borderRadius: 'var(--radius-sm)', textDecoration: 'none', fontSize: 'var(--text-xs)', fontWeight: 800 }}
                    >
                      <Code2 size={14} /> Open Workspace
                    </Link>
                  </div>
                </div>

                {codeProjectsError && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-xs)', color: '#ef4444' }}>
                    <AlertTriangle size={14} /> {codeProjectsError}
                  </span>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
                  {codeProjects.map((project) => (
                    <div key={project.id} style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px' }}>
                        <strong style={{ fontSize: 'var(--text-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.name}</strong>
                        <span style={{ color: project.status === 'active' ? 'var(--color-success)' : 'var(--color-text-secondary)', fontSize: '10px', fontWeight: 800, textTransform: 'uppercase' }}>{project.status || 'active'}</span>
                      </div>
                      <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                        {(project.file_ids || []).length} Code file{(project.file_ids || []).length === 1 ? '' : 's'} attached
                      </span>
                      {project.repo_url && (
                        <span style={{ color: 'var(--color-text-tertiary)', fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.repo_url}</span>
                      )}
                      <span style={{ color: 'var(--color-text-tertiary)', fontSize: '10px' }}>
                        Last opened: {project.last_opened_at ? new Date(project.last_opened_at).toLocaleString() : 'Not opened yet'}
                      </span>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
                        <button
                          onClick={() => renameCodeProject(project)}
                          style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '6px 10px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '10px', fontWeight: 800 }}
                        >
                          Rename
                        </button>
                        <button
                          onClick={() => archiveCodeProject(project)}
                          style={{ background: 'transparent', border: '1px solid rgba(239, 68, 68, 0.45)', color: '#f87171', padding: '6px 10px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '10px', fontWeight: 800 }}
                        >
                          Archive
                        </button>
                      </div>
                    </div>
                  ))}
                  {!codeProjectsLoading && codeProjects.length === 0 && (
                    <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                      No Arceus Code projects yet. Open the workspace and create your first project.
                    </div>
                  )}
                </div>
              </div>
            )}

            {(!isElectron || activeTab === 'code') && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid var(--color-border)', paddingTop: '16px' }}>
                <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Connected Developer Tools</h2>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  backgroundColor: 'var(--color-bg-tertiary)',
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--color-border)',
                  marginTop: '8px'
                }}>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <div style={{ width: '28px', height: '28px', backgroundColor: '#24292e', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 'bold', fontSize: '14px' }}>G</div>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>GitHub integration</span>
                      <span style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>Status: {githubConnected ? 'Active · Connected to 12 repos' : 'Disconnected'}</span>
                    </div>
                  </div>
                  <button
                    style={{ backgroundColor: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '6px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600 }}
                    onClick={() => setGithubConnected((value) => !value)}
                  >
                    {githubConnected ? 'Disconnect' : 'Reconnect'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function VaultSection() {
  const [vaultExists, setVaultExists] = useState<boolean | null>(null);
  const [salt, setSalt] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [unlocked, setUnlocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const checkStatus = async () => {
    try {
      const res = await apiRequest('/api/v1/vault/status');
      setVaultExists(res.exists);
      if (res.exists) {
        setSalt(res.salt);
      }
      setUnlocked(!!getVaultKey());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch vault status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (!password) {
      setError('Password cannot be empty');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const generatedSalt = generateSaltHex();
      const derivedKey = await deriveVaultKey(password, generatedSalt);

      // Call setup API
      await apiRequest('/api/v1/vault/setup', {
        method: 'POST',
        body: JSON.stringify({
          salt: generatedSalt,
        }),
      });

      // Save key in sessionStorage
      setVaultKey(derivedKey);
      setUnlocked(true);
      setVaultExists(true);
      setSalt(generatedSalt);
      setSuccess('Zero-knowledge vault created successfully! All personal data will be encrypted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vault setup failed');
    } finally {
      setLoading(false);
    }
  };

  const handleUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (!password) {
      setError('Password cannot be empty');
      return;
    }
    if (!salt) {
      setError('Vault configuration error: Salt not found');
      return;
    }
    setLoading(true);
    try {
      const derivedKey = await deriveVaultKey(password, salt);
      setVaultKey(derivedKey);
      setUnlocked(true);
      setSuccess('Vault unlocked successfully.');
      window.dispatchEvent(new Event('vault-unlocked'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unlock vault');
    } finally {
      setLoading(false);
    }
  };

  const handleLock = () => {
    clearVaultKey();
    setUnlocked(false);
    setPassword('');
    setConfirmPassword('');
    setSuccess('Vault locked successfully. Session key cleared.');
    window.dispatchEvent(new Event('vault-locked'));
  };

  if (loading && vaultExists === null) {
    return <div>Loading vault settings...</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>🔒 Zero-Knowledge Privacy Vault</h2>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', margin: '4px 0 0 0' }}>
          Protect your personal assistant memory, schedules, and goals with AES-256 encryption. Only you hold the key. We cannot read your data.
        </p>
      </div>

      {error && (
        <div style={{ padding: '10px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '4px', color: '#ef4444', fontSize: 'var(--text-xs)' }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: '10px', background: 'rgba(34, 197, 94, 0.1)', border: '1px solid #22c55e', borderRadius: '4px', color: '#22c55e', fontSize: 'var(--text-xs)' }}>
          {success}
        </div>
      )}

      {vaultExists ? (
        unlocked ? (
          <div style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#22c55e' }}>
              <CheckCircle2 size={16} />
              <strong style={{ fontSize: 'var(--text-sm)' }}>Vault is Active & Unlocked</strong>
            </div>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', margin: 0 }}>
              Your session key is loaded in memory. All read and write operations on personal assistant data are fully encrypted in the database.
            </p>
            <button
              onClick={handleLock}
              style={{ alignSelf: 'flex-start', background: 'transparent', border: '1px solid #ef4444', color: '#ef4444', padding: '8px 14px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
            >
              Lock Vault (Clear Session Key)
            </button>
          </div>
        ) : (
          <form onSubmit={handleUnlock} style={{ display: 'flex', flexDirection: 'column', gap: '12px', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
            <strong style={{ fontSize: 'var(--text-sm)' }}>Unlock Your Privacy Vault</strong>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', margin: 0 }}>
              Enter your vault passphrase to derive your encryption key. Your key never leaves your browser.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>VAULT PASSPHRASE</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter passphrase"
                style={{ width: '100%', maxWidth: '320px', background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '4px', padding: '8px 12px', color: 'var(--color-text-primary)', outline: 'none' }}
              />
            </div>
            <button
              type="submit"
              style={{ alignSelf: 'flex-start', background: 'var(--color-accent-primary)', border: '1px solid var(--color-accent-primary)', color: 'white', padding: '8px 16px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700 }}
            >
              Unlock Vault
            </button>
          </form>
        )
      ) : (
        <form onSubmit={handleSetup} style={{ display: 'flex', flexDirection: 'column', gap: '16px', background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
          <strong style={{ fontSize: 'var(--text-sm)', color: 'var(--color-warning)' }}>⚠️ Setup Privacy Vault (Highly Recommended)</strong>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', margin: 0 }}>
            Creating a vault password derives a secure cryptographic key that only you hold. Without this key, your personal data stored on our servers is unreadable gibberish.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>CHOOSE VAULT PASSPHRASE</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Choose a strong passphrase"
                style={{ width: '100%', maxWidth: '320px', background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '4px', padding: '8px 12px', color: 'var(--color-text-primary)', outline: 'none' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>CONFIRM VAULT PASSPHRASE</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm passphrase"
                style={{ width: '100%', maxWidth: '320px', background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '4px', padding: '8px 12px', color: 'var(--color-text-primary)', outline: 'none' }}
              />
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>
              ⚠️ WARNING: If you forget this passphrase, your encrypted data cannot be recovered.
            </span>
            <button
              type="submit"
              style={{ alignSelf: 'flex-start', background: '#10b981', border: '1px solid #10b981', color: 'white', padding: '8px 16px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 800 }}
            >
              Create Privacy Vault
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
