'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Bell,
  BriefcaseBusiness,
  CalendarClock,
  Cpu,
  Mic,
  PauseCircle,
  PhoneCall,
  Settings,
  ShieldAlert,
  Square,
} from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

const products = [
  { name: 'NEXUS Code', href: '/workspace', icon: Cpu, detail: 'Code, design, research, deploy, and review from one workspace' },
  { name: 'NEXUS PA', href: '/pa', icon: BriefcaseBusiness, detail: 'Always-on personal assistant OS layer', live: true },
  { name: 'NEXUS Interview', href: '/interview', icon: Mic, detail: 'Resume-aware live coaching and interview preparation' },
];

type PAStatus = {
  state: 'active' | 'paused' | 'sleep' | 'stopped';
  status_label: string;
  monitoring: boolean;
  call_ai: string;
  voice: string;
  next_event?: { title: string; time: string } | null;
  pending_delegations: number;
  unread_alerts: number;
  active_schedules: number;
  daily_brief: string;
  locked?: boolean;
};

type CompetitivePosition = {
  summary: string;
  capabilities: Array<{
    area: string;
    status: string;
    score: number;
    next: string;
  }>;
  strategic_gaps: string[];
};

const fallbackStatus: PAStatus = {
  state: 'active',
  status_label: 'Active',
  monitoring: true,
  call_ai: 'ready',
  voice: 'ready',
  next_event: null,
  pending_delegations: 0,
  unread_alerts: 0,
  active_schedules: 0,
  daily_brief: 'NEXUS PA is ready. Connect calendar, tasks, and memories for a stronger daily brief.',
};

export default function HubPage() {
  const [status, setStatus] = useState<PAStatus>(fallbackStatus);
  const [competitive, setCompetitive] = useState<CompetitivePosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStatus = async () => {
    try {
      const data = await apiRequest('/api/v1/pa/os-status');
      setStatus(data.locked ? { ...fallbackStatus, state: 'stopped', status_label: 'Locked', monitoring: false } : data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PA OS status is unavailable.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
    apiRequest('/api/v1/competitive-position')
      .then((data) => setCompetitive(data.competitive_position))
      .catch(() => setCompetitive(null));
  }, []);

  const setPAState = async (state: PAStatus['state']) => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/pa/os-status', {
        method: 'POST',
        body: JSON.stringify({ state }),
      });
      setStatus(data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update PA state.');
    } finally {
      setLoading(false);
    }
  };

  const emergencyStop = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/pa/emergency-stop', { method: 'POST' });
      setStatus(data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Emergency stop failed.');
    } finally {
      setLoading(false);
    }
  };

  const nextLabel = useMemo(() => {
    if (!status.next_event) return 'No scheduled item today';
    const date = new Date(status.next_event.time);
    const time = Number.isNaN(date.getTime()) ? 'soon' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${status.next_event.title} at ${time}`;
  }, [status.next_event]);

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.osTopBar}>
          <div>
            <div className={styles.eyebrow}>NEXUS PA OS</div>
            <h1 className={styles.title}>Home Screen</h1>
          </div>
          <div className={styles.osControls}>
            <span className={`${styles.statusPill} ${styles[`status_${status.state}`]}`}>
              <span className={styles.statusDot} /> PA: {status.status_label}
            </span>
            <button className={styles.secondaryButton} type="button" onClick={() => setPAState(status.state === 'paused' ? 'active' : 'paused')} disabled={loading}>
              <PauseCircle size={16} /> {status.state === 'paused' ? 'Resume' : 'Pause'}
            </button>
            <button className={styles.dangerButton} type="button" onClick={emergencyStop} disabled={loading}>
              <ShieldAlert size={16} /> Emergency Stop
            </button>
          </div>
        </section>

        <section className={styles.paStatusStrip}>
          <div className={styles.statusMetric}>
            <CalendarClock size={18} />
            <span>Next: {nextLabel}</span>
          </div>
          <div className={styles.statusMetric}>
            <PhoneCall size={18} />
            <span>Call AI: {status.call_ai}</span>
          </div>
          <div className={styles.statusMetric}>
            <Mic size={18} />
            <span>Voice: {status.voice}</span>
          </div>
          <div className={styles.statusMetric}>
            <Bell size={18} />
            <span>{status.unread_alerts} alerts · {status.pending_delegations} pending</span>
          </div>
        </section>

        {error && <section className={styles.errorStrip}>{error}</section>}

        <section className={styles.hubHero}>
          <div className={styles.eyebrow}>NEXUS AI Platform</div>
          <h2 className={styles.title}>Choose the workspace you need</h2>
          <p className={styles.subtitle}>A focused signed-in hub for Code, PA, and Interview. Design, research, deploy, and planning agents now live inside NEXUS Code instead of separate public products.</p>
        </section>

        <section className={styles.productGrid}>
          {products.map((product) => {
            const Icon = product.icon;
            const isLivePA = product.live && status.monitoring;
            return (
              <Link className={`${styles.productCard} ${isLivePA ? styles.productCardLive : ''}`} href={product.href} key={product.name}>
                <div className={styles.productCardHeader}>
                  <Icon size={30} />
                  {product.live && (
                    <span className={isLivePA ? styles.liveBadge : styles.offBadge}>
                      {isLivePA ? <Activity size={13} /> : <Square size={12} />} {status.monitoring ? 'LIVE' : status.status_label}
                    </span>
                  )}
                </div>
                <h2>{product.name}</h2>
                <p>{product.detail}</p>
              </Link>
            );
          })}
        </section>

        <section className={styles.dailyBriefPanel}>
          <div>
            <div className={styles.eyebrow}>Today's AI Brief</div>
            <p>{status.daily_brief}</p>
          </div>
          <div className={styles.briefStats}>
            <span>{status.active_schedules} schedules</span>
            <span>{status.pending_delegations} open tasks</span>
            <span>{status.unread_alerts} overdue</span>
          </div>
        </section>

        {competitive && (
          <section className={styles.commandPanel}>
            <div className={styles.commandHeader}>
              <div>
                <div className={styles.eyebrow}>Competitive Position</div>
                <h2 className={styles.compactTitle}>Where NEXUS stands now</h2>
              </div>
              <Link className={styles.secondaryButton} href="/settings">View system settings</Link>
            </div>
            <p className={styles.meta}>{competitive.summary}</p>
            <div className={styles.capabilityGrid}>
              {competitive.capabilities.slice(0, 4).map((item) => (
                <div className={styles.capabilityCard} key={item.area}>
                  <div className={styles.capabilityHead}>
                    <strong>{item.area}</strong>
                    <span>{item.score}/10</span>
                  </div>
                  <span className={styles.meta}>{item.status.replaceAll('_', ' ')}</span>
                  <p>{item.next}</p>
                </div>
              ))}
            </div>
            <div className={styles.briefStats}>
              {competitive.strategic_gaps.slice(0, 3).map((gap) => (
                <span key={gap}>{gap}</span>
              ))}
            </div>
          </section>
        )}

        <section className={styles.actionBar}>
          <Link className={styles.secondaryButton} href="/settings"><Settings size={16} /> Settings</Link>
          <button className={styles.secondaryButton} type="button" onClick={() => setPAState('active')} disabled={loading}>
            <Mic size={16} /> Voice Command Ready
          </button>
        </section>
      </main>
    </AppShell>
  );
}
