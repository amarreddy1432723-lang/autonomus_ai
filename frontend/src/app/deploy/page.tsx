'use client';

import { useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

export default function DeployPage() {
  const [projectType, setProjectType] = useState('Next.js frontend plus FastAPI backend');
  const [repoContext, setRepoContext] = useState('Uses Railway for backend services and Next.js rewrites for API proxying.');
  const [analysis, setAnalysis] = useState('');
  const [loading, setLoading] = useState(false);

  const analyze = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/deploy/analyze', {
        method: 'POST',
        body: JSON.stringify({ project_type: projectType, repo_context: repoContext }),
      });
      setAnalysis(JSON.stringify(data, null, 2));
    } catch (error) {
      setAnalysis(error instanceof Error ? error.message : 'Deploy analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const start = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/deploy/start', {
        method: 'POST',
        body: JSON.stringify({ project_type: projectType, repo_context: repoContext }),
      });
      setAnalysis(JSON.stringify(data, null, 2));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>NEXUS Deploy Engine</div>
          <h1 className={styles.title}>Analyze deployment paths before touching production.</h1>
          <p className={styles.subtitle}>Deployment actions are intentionally approval-gated because they can change live infrastructure and secrets.</p>
        </section>
        <section className={styles.grid}>
          <div className={styles.panel}>
            <h2>Project</h2>
            <div className={styles.form}>
              <input className={styles.input} value={projectType} onChange={(event) => setProjectType(event.target.value)} />
              <textarea className={styles.textarea} value={repoContext} onChange={(event) => setRepoContext(event.target.value)} />
              <button className={styles.button} disabled={loading} onClick={analyze}>Analyze</button>
              <button className={styles.button} disabled={loading} onClick={start}>Prepare Deployment</button>
            </div>
          </div>
          <pre className={styles.output}>{analysis || 'Deployment analysis will appear here.'}</pre>
        </section>
      </main>
    </AppShell>
  );
}
