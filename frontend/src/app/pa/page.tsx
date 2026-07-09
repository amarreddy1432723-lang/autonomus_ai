'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Bell, Calendar, CheckCircle2, Lock, Mic, RefreshCw, Search, Sparkles } from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

export default function PAPage() {
  const [brief, setBrief] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadBrief = async () => {
    setLoading(true);
    try {
      setBrief(await apiRequest('/api/v1/pa/daily-brief'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBrief();
  }, []);

  if (brief?.locked) {
    return (
      <AppShell>
        <main className={styles.page}>
          <section className={styles.lockPanel}>
            <Lock size={34} />
            <h1>NEXUS PA is a Pro feature</h1>
            <p>Unlock morning briefs, smart scheduling, meeting prep, delegation, and weekly reflection.</p>
            <Link className={styles.button} href="/settings">Upgrade to Pro</Link>
          </section>
        </main>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.paCommandCenter}>
          <div>
            <span className={styles.eyebrow}>NEXUS PA OS</span>
            <h1 className={styles.compactTitle}>What needs attention?</h1>
          </div>
          <label className={styles.paCommandInput}>
            <Search size={16} />
            <input readOnly placeholder="Ask NEXUS PA to plan, remember, schedule, or remind..." />
          </label>
          <button className={styles.voiceButton} type="button">
            <Mic size={16} />
            Voice ready
          </button>
        </section>

        <section className={styles.paQuickGrid} aria-label="NEXUS PA quick actions">
          <Link href="/tasks">
            <CheckCircle2 size={17} />
            <span>Tasks</span>
          </Link>
          <Link href="/calendar">
            <Calendar size={17} />
            <span>Calendar</span>
          </Link>
          <Link href="/memory">
            <Sparkles size={17} />
            <span>Memory</span>
          </Link>
          <Link href="/approvals">
            <Bell size={17} />
            <span>Alerts</span>
          </Link>
        </section>

        <section className={styles.commandPanel}>
          <div className={styles.commandHeader}>
            <div>
              <span className={styles.eyebrow}>NEXUS PA</span>
              <h1 className={styles.compactTitle}>Morning brief</h1>
            </div>
            <button className={styles.secondaryButton} onClick={loadBrief}><RefreshCw size={15} /> Refresh</button>
          </div>
          {loading && <div className={styles.skeletonCard} />}
          {brief && !loading && (
            <div className={styles.grid}>
              <div className={styles.phaseCard}>
                <h2>Today</h2>
                <div className={styles.phaseList}>
                  {(brief.schedule || []).map((item: any) => (
                    <div className={styles.item} key={item.id}>
                      <strong>{new Date(item.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong>
                      <p>{item.title}</p>
                    </div>
                  ))}
                  {(!brief.schedule || brief.schedule.length === 0) && <p className={styles.meta}>No scheduled items today.</p>}
                </div>
              </div>
              <div className={styles.phaseCard}>
                <h2>Priorities</h2>
                <div className={styles.phaseList}>
                  {(brief.priorities || []).map((task: any, index: number) => (
                    <div className={styles.item} key={task.id}>
                      <strong>{index + 1}. {task.title}</strong>
                      <p>{task.status} · score {Math.round(task.priority_score)}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div className={styles.phaseCard}>
                <h2>NEXUS noticed</h2>
                <p>{brief.insight}</p>
                <p className={styles.meta}>Suggested focus block: {brief.suggested_focus_block}</p>
                <div className={styles.inlineActions}>
                  <Link className={styles.secondaryButton} href="/pa/planner"><Calendar size={15} /> Adjust schedule</Link>
                  <Link className={styles.secondaryButton} href="/pa/reflection"><Sparkles size={15} /> Reflection</Link>
                </div>
              </div>
            </div>
          )}
        </section>
        <nav className={styles.mobilePaDock} aria-label="NEXUS PA mobile navigation">
          <Link href="/pa"><Sparkles size={17} /> Today</Link>
          <Link href="/tasks"><CheckCircle2 size={17} /> Tasks</Link>
          <Link href="/calendar"><Calendar size={17} /> Calendar</Link>
          <Link href="/memory"><Search size={17} /> Memory</Link>
        </nav>
      </main>
    </AppShell>
  );
}
