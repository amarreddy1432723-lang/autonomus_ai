'use client';

import { useEffect, useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

export default function InternetPage() {
  const [query, setQuery] = useState('top free PostgreSQL hosting options for a Next.js app');
  const [projectType, setProjectType] = useState('Next.js app with FastAPI backend');
  const [needs, setNeeds] = useState('database, hosting, auth, storage');
  const [report, setReport] = useState('');
  const [tiers, setTiers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiRequest('/api/v1/free-tiers/catalog').then((data) => setTiers(data.items || [])).catch(() => setTiers([]));
  }, []);

  const research = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/internet/research', {
        method: 'POST',
        body: JSON.stringify({ query }),
      });
      setReport(data.report || '');
    } catch (error) {
      setReport(error instanceof Error ? error.message : 'Research failed');
    } finally {
      setLoading(false);
    }
  };

  const recommend = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/free-tiers/recommend', {
        method: 'POST',
        body: JSON.stringify({ project_type: projectType, needs }),
      });
      setTiers(data.items || []);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>NEXUS Internet Agent</div>
          <h1 className={styles.title}>Research, compare, and prepare free-tier services.</h1>
          <p className={styles.subtitle}>Live research uses the existing SERPER search path when configured. Setup actions remain approval-gated.</p>
        </section>
        <section className={styles.grid}>
          <div className={styles.panel}>
            <h2>Deep Research</h2>
            <div className={styles.form}>
              <textarea className={styles.textarea} value={query} onChange={(event) => setQuery(event.target.value)} />
              <button className={styles.button} disabled={loading} onClick={research}>Research</button>
            </div>
          </div>
          <div className={styles.panel}>
            <h2>Free Tier Maximizer</h2>
            <div className={styles.form}>
              <input className={styles.input} value={projectType} onChange={(event) => setProjectType(event.target.value)} />
              <input className={styles.input} value={needs} onChange={(event) => setNeeds(event.target.value)} />
              <button className={styles.button} disabled={loading} onClick={recommend}>Recommend Stack</button>
            </div>
          </div>
        </section>
        <section className={styles.grid}>
          <div className={styles.output}>{report || 'Research report will appear here.'}</div>
          <div className={styles.list}>
            {tiers.map((tier) => (
              <div className={styles.item} key={tier.name}>
                <h3>{tier.name}</h3>
                <p>{tier.best_for}</p>
                <div className={styles.meta}>{tier.category} · {tier.free_tier}</div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </AppShell>
  );
}
