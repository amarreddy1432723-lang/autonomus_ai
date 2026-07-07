'use client';

import { useEffect, useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

export default function IntelligencePage() {
  const [context, setContext] = useState('code deployment interview usage');
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [insights, setInsights] = useState<any>(null);

  const load = async () => {
    const [suggestionData, insightData] = await Promise.all([
      apiRequest(`/api/v1/intelligence/suggestions?context=${encodeURIComponent(context)}`),
      apiRequest('/api/v1/intelligence/insights'),
    ]);
    setSuggestions(suggestionData.items || []);
    setInsights(insightData);
  };

  useEffect(() => {
    load().catch(() => {
      setSuggestions([]);
      setInsights(null);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const feedback = async (id: string, value: string) => {
    await apiRequest('/api/v1/intelligence/feedback', {
      method: 'POST',
      body: JSON.stringify({ suggestion_id: id, feedback: value }),
    });
    setSuggestions((items) => items.filter((item) => item.id !== id));
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>NEXUS Proactive Intelligence</div>
          <h1 className={styles.title}>Ranked next actions before you ask.</h1>
          <p className={styles.subtitle}>Suggestions are generated from context now, and can later learn from accepted and dismissed actions.</p>
        </section>
        <section className={styles.panel}>
          <h2>Suggestion Context</h2>
          <div className={styles.form}>
            <input className={styles.input} value={context} onChange={(event) => setContext(event.target.value)} />
            <button className={styles.button} onClick={load}>Refresh Suggestions</button>
          </div>
        </section>
        <section className={styles.grid}>
          <div className={styles.list}>
            {suggestions.map((suggestion) => (
              <div className={styles.item} key={suggestion.id}>
                <h3>{suggestion.title}</h3>
                <p>{suggestion.detail}</p>
                <div className={styles.meta}>{suggestion.category} · priority {suggestion.priority}</div>
                <button className={styles.button} onClick={() => feedback(suggestion.id, 'accepted')}>Accept</button>
                <button className={styles.button} onClick={() => feedback(suggestion.id, 'dismissed')}>Dismiss</button>
              </div>
            ))}
          </div>
          <pre className={styles.output}>{insights ? JSON.stringify(insights, null, 2) : 'Insights will appear here.'}</pre>
        </section>
      </main>
    </AppShell>
  );
}
