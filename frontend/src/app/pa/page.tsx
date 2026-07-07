'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Calendar, Lock, RefreshCw, Sparkles } from 'lucide-react';
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
      </main>
    </AppShell>
  );
}
