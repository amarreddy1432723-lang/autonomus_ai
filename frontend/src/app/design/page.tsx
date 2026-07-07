'use client';

import { useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

export default function DesignPage() {
  const [description, setDescription] = useState('Design a professional dark SaaS dashboard for an AI productivity platform with usage charts and approval queue.');
  const [outputType, setOutputType] = useState('page');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    setResult('');
    try {
      const path = outputType === 'critique' ? '/api/v1/design/critique' : outputType === 'animation' ? '/api/v1/design/animate' : '/api/v1/design/generate-page';
      const data = await apiRequest(path, {
        method: 'POST',
        body: JSON.stringify({ description, output_type: outputType }),
      });
      setResult(data.content || JSON.stringify(data, null, 2));
    } catch (error) {
      setResult(error instanceof Error ? error.message : 'Design generation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>NEXUS UI/UX Studio</div>
          <h1 className={styles.title}>Generate professional product UI structure, motion, and critique.</h1>
          <p className={styles.subtitle}>This first pass returns production-ready direction and starter code through the existing model router.</p>
        </section>
        <section className={styles.grid}>
          <div className={styles.panel}>
            <h2>Design Brief</h2>
            <div className={styles.form}>
              <select className={styles.select} value={outputType} onChange={(event) => setOutputType(event.target.value)}>
                <option value="page">Full Page</option>
                <option value="ui">Component System</option>
                <option value="animation">Animation Pass</option>
                <option value="critique">UX Critique</option>
              </select>
              <textarea className={styles.textarea} value={description} onChange={(event) => setDescription(event.target.value)} />
              <button className={styles.button} disabled={loading} onClick={generate}>Generate Design</button>
            </div>
          </div>
          <div className={styles.output}>{result || 'Design output will appear here.'}</div>
        </section>
      </main>
    </AppShell>
  );
}
