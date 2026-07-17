'use client';

import Link from 'next/link';
import type { CSSProperties } from 'react';
import { AlertTriangle, MonitorCheck, RefreshCw, TerminalSquare } from 'lucide-react';
import type { ServiceHealthSnapshot } from '../utils/serviceHealth';

type ServiceRecoveryBannerProps = {
  health: ServiceHealthSnapshot;
  compact?: boolean;
  onRetry?: () => void;
  onOpenTerminal?: () => void;
  onOpenDiagnostics?: () => void;
};

export default function ServiceRecoveryBanner({
  health,
  compact = false,
  onRetry,
  onOpenTerminal,
  onOpenDiagnostics,
}: ServiceRecoveryBannerProps) {
  if (health.state === 'online') return null;

  const tone = health.state === 'auth_required' ? 'warning' : health.state === 'partially_online' ? 'warning' : 'danger';
  const background = tone === 'warning' ? 'rgba(234, 179, 8, 0.08)' : 'rgba(239, 68, 68, 0.08)';
  const border = tone === 'warning' ? 'rgba(234, 179, 8, 0.35)' : 'rgba(239, 68, 68, 0.32)';
  const accent = tone === 'warning' ? '#facc15' : '#fca5a5';

  return (
    <section
      role="status"
      style={{
        display: 'flex',
        alignItems: compact ? 'center' : 'flex-start',
        justifyContent: 'space-between',
        gap: 14,
        border: `1px solid ${border}`,
        background,
        borderRadius: 10,
        padding: compact ? '9px 10px' : '12px 14px',
      }}
    >
      <div style={{ display: 'flex', gap: 10, minWidth: 0 }}>
        <AlertTriangle size={16} color={accent} style={{ flex: '0 0 auto', marginTop: compact ? 1 : 2 }} />
        <div style={{ display: 'grid', gap: 3, minWidth: 0 }}>
          <strong style={{ color: '#f6f7fb', fontSize: compact ? 12 : 13 }}>{health.label}</strong>
          <span style={{ color: '#a8b0bf', fontSize: 12, lineHeight: 1.45 }}>{health.detail}</span>
          {health.state === 'offline_local_only' && (
            <span style={{ color: '#8b95a7', fontSize: 11 }}>
              Local folder, editor, and terminal stay available. Cloud agent, GitHub, billing, managed models, and preview verification are paused.
            </span>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', flex: '0 0 auto' }}>
        {health.state === 'auth_required' && (
          <Link href="/auth/desktop" style={actionStyle('primary')}>
            <MonitorCheck size={13} />
            Connect account
          </Link>
        )}
        {onRetry && (
          <button type="button" style={actionStyle('secondary')} onClick={onRetry}>
            <RefreshCw size={13} />
            Retry services
          </button>
        )}
        {onOpenTerminal && (
          <button type="button" style={actionStyle('secondary')} onClick={onOpenTerminal}>
            <TerminalSquare size={13} />
            Use local terminal
          </button>
        )}
        {onOpenDiagnostics && (
          <button type="button" style={actionStyle('secondary')} onClick={onOpenDiagnostics}>
            Open diagnostics
          </button>
        )}
      </div>
    </section>
  );
}

function actionStyle(kind: 'primary' | 'secondary'): CSSProperties {
  return {
    minHeight: 28,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    border: '1px solid',
    borderColor: kind === 'primary' ? '#7c6cf0' : 'rgba(255,255,255,0.1)',
    background: kind === 'primary' ? '#7c6cf0' : 'rgba(255,255,255,0.04)',
    color: kind === 'primary' ? 'white' : '#d8deea',
    borderRadius: 7,
    padding: '0 9px',
    fontSize: 11,
    fontWeight: 800,
    cursor: 'pointer',
    textDecoration: 'none',
    whiteSpace: 'nowrap',
  };
}
