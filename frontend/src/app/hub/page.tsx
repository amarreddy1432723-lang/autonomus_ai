'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Bell,
  BrainCircuit,
  BriefcaseBusiness,
  CalendarClock,
  Cpu,
  Globe2,
  Mic,
  PauseCircle,
  Palette,
  PhoneCall,
  Rocket,
  Settings,
  ShieldAlert,
  Square,
} from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

const products = [
  { name: 'NEXUS Code', href: '/studio', icon: Cpu, detail: 'AI coding engine, planning, patches, deploy handoff' },
  { name: 'NEXUS PA', href: '/pa', icon: BriefcaseBusiness, detail: 'Always-on personal assistant OS layer', live: true },
  { name: 'Interview', href: '/interview', icon: Mic, detail: 'Resume-aware live coaching and practice' },
  { name: 'Design', href: '/design', icon: Palette, detail: 'UI/UX variants and implementation handoff' },
  { name: 'Deploy', href: '/deploy', icon: Rocket, detail: 'Analyze and prepare production deployments' },
  { name: 'Research', href: '/internet', icon: Globe2, detail: 'Relevant live research without noisy updates' },
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
          <h2 className={styles.title}>Your AI-powered product suite</h2>
          <p className={styles.subtitle}>One shared intelligence layer across coding, personal assistance, interviews, design, deployment, research, and the always-on PA OS.</p>
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

        <section className={styles.actionBar}>
          <Link className={styles.secondaryButton} href="/life-graph"><BrainCircuit size={16} /> Life Graph</Link>
          <Link className={styles.secondaryButton} href="/settings"><Settings size={16} /> Settings</Link>
          <button className={styles.secondaryButton} type="button" onClick={() => setPAState('active')} disabled={loading}>
            <Mic size={16} /> Voice Command Ready
          </button>
        </section>
      </main>
    </AppShell>
  );
}
