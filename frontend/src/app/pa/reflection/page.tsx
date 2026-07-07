'use client';

import { useEffect, useState } from 'react';
import AppShell from '../../../components/AppShell';
import { apiRequest } from '../../../utils/api';
import styles from '../../nexus.module.css';

export default function PAReflectionPage() {
  const [reflection, setReflection] = useState<any>(null);

  useEffect(() => {
    apiRequest('/api/v1/pa/weekly-reflection').then(setReflection).catch((error) => setReflection({ error: error.message }));
  }, []);

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.commandPanel}>
          <span className={styles.eyebrow}>NEXUS PA</span>
          <h1 className={styles.compactTitle}>Weekly reflection</h1>
        </section>
        {reflection?.locked && <section className={styles.lockPanel}>Upgrade to Pro to unlock weekly reflections.</section>}
        {reflection?.error && <section className={styles.phaseCard}>{reflection.error}</section>}
        {reflection && !reflection.locked && !reflection.error && (
          <section className={styles.grid}>
            <div className={styles.phaseCard}><h2>Completed</h2><p>{reflection.tasks_completed} tasks</p></div>
            <div className={styles.phaseCard}><h2>Overdue</h2><p>{reflection.tasks_overdue} tasks</p></div>
            <div className={styles.phaseCard}><h2>What worked</h2><p>{reflection.what_worked}</p></div>
            <div className={styles.phaseCard}><h2>What did not</h2><p>{reflection.what_didnt}</p></div>
            <div className={styles.phaseCard}>
              <h2>Recommendations</h2>
              <ul>
                {(reflection.ai_recommendations || []).map((item: string) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </section>
        )}
      </main>
    </AppShell>
  );
}
