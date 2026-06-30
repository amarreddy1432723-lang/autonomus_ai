'use client';

import React, { useEffect, useState } from 'react';
import AppShell from '../../components/AppShell';
import { AlertTriangle, Bell, CheckCircle2, Play, RefreshCw, Shield, User } from 'lucide-react';
import { apiRequest } from '../../utils/api';

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

const autonomyOptions: { value: AutonomyLevel; label: string }[] = [
  { value: 'observer', label: 'Observer' },
  { value: 'assistant', label: 'Assistant' },
  { value: 'partner', label: 'Partner' },
  { value: 'chief_of_staff', label: 'Chief of staff' },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'autonomy' | 'profile' | 'notifications'>('autonomy');
  const [githubConnected, setGithubConnected] = useState(true);
  const [autonomyStatus, setAutonomyStatus] = useState<AutonomyStatus | null>(null);
  const [dryRunResult, setDryRunResult] = useState<string>('');
  const [loadingAutonomy, setLoadingAutonomy] = useState(true);
  const [autonomyError, setAutonomyError] = useState('');

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

  useEffect(() => {
    loadAutonomyStatus();
  }, []);

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

  const tabButtonStyle = (tab: typeof activeTab) => ({
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
            <button style={tabButtonStyle('autonomy')} onClick={() => setActiveTab('autonomy')}>
              <Shield size={14} /> Autonomy policy
            </button>
            <button style={tabButtonStyle('profile')} onClick={() => setActiveTab('profile')}>
              <User size={14} /> Profile settings
            </button>
            <button style={tabButtonStyle('notifications')} onClick={() => setActiveTab('notifications')}>
              <Bell size={14} /> Notifications
            </button>
          </div>

          {/* Settings Content Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
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

            {/* INTEGRATIONS SYNC */}
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
          </div>
        </div>
      </div>
    </AppShell>
  );
}
