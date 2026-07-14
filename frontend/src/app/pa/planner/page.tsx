'use client';

import { useState } from 'react';
import { CalendarClock } from 'lucide-react';
import AppShell from '../../../components/AppShell';
import { apiRequest } from '../../../utils/api';
import styles from '../../nexus.module.css';

export default function PAPlannerPage() {
  const [task, setTask] = useState('Schedule a 1-hour meeting with the design team this week');
  const [duration, setDuration] = useState(60);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const optimize = async () => {
    setError('');
    setResult(null);
    try {
      setResult(await apiRequest('/api/v1/pa/schedule', {
        method: 'POST',
        body: JSON.stringify({ task, duration_minutes: duration }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scheduling requires Pro');
    }
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.commandPanel}>
          <div className={styles.commandHeader}>
            <div>
              <span className={styles.eyebrow}>Arceus PA</span>
              <h1 className={styles.compactTitle}>Smart scheduling</h1>
            </div>
            <button className={styles.button} onClick={optimize}><CalendarClock size={16} /> Optimize</button>
          </div>
          <div className={styles.promptRow}>
            <textarea className={styles.largePrompt} value={task} onChange={(event) => setTask(event.target.value)} />
            <input className={styles.input} type="number" value={duration} onChange={(event) => setDuration(Number(event.target.value))} min={15} step={15} />
          </div>
        </section>
        {result && (
          <section className={styles.summaryCard}>
            <h2>Recommended slot</h2>
            <p>{new Date(result.recommended_slot).toLocaleString()}</p>
            <p>{result.reason}</p>
          </section>
        )}
        {error && <section className={styles.phaseCard}>{error}</section>}
      </main>
    </AppShell>
  );
}
