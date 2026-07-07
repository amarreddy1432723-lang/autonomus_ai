'use client';

import { useState } from 'react';
import Link from 'next/link';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

const pillars = [
  { title: 'Code Engine', href: '/workspace', detail: 'Multi-file plans, patches, explanations, tests, and approval-first apply flow.' },
  { title: 'Internet Agent', href: '/internet', detail: 'Live research, URL extraction, and free-tier recommendations.' },
  { title: 'Design Studio', href: '/design', detail: 'Generate UI structures, animation guidance, critiques, and component plans.' },
  { title: 'Deploy Engine', href: '/deploy', detail: 'Analyze projects, choose providers, and prepare approval-gated deployments.' },
  { title: 'Intelligence', href: '/intelligence', detail: 'Ranked next-action suggestions for code, deployment, usage, and safety.' },
  { title: 'Interview Assist', href: '/interview', detail: 'Resume-aware live interview coaching with planning and fast spoken answers.' },
];

export default function StudioPage() {
  const [prompt, setPrompt] = useState('Build a secure FastAPI endpoint and explain the tradeoffs.');
  const [routeResult, setRouteResult] = useState<any>(null);
  const [blendResult, setBlendResult] = useState<any>(null);
  const [memorySummary, setMemorySummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const routeModel = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/api/v1/models/route', {
        method: 'POST',
        body: JSON.stringify({ prompt, speed_priority: true }),
      });
      setRouteResult(data);
    } finally {
      setLoading(false);
    }
  };

  const blendAnswer = async () => {
    setLoading(true);
    setBlendResult(null);
    try {
      const data = await apiRequest('/api/v1/models/blend', {
        method: 'POST',
        body: JSON.stringify({ prompt }),
      });
      setBlendResult(data);
      setRouteResult({ task_type: data.task_type, selected_model: data.selected_model });
    } finally {
      setLoading(false);
    }
  };

  const loadMemorySummary = async () => {
    const data = await apiRequest('/api/v1/memories/summary');
    setMemorySummary(data);
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>NEXUS AI Studio</div>
          <h1 className={styles.title}>One agentic command center for building, researching, designing, deploying, and preparing.</h1>
          <p className={styles.subtitle}>
            This studio activates the new NEXUS pillars on top of the existing my-ai architecture: model routing, memory, file RAG, approvals, workspace, and live search.
          </p>
        </section>
        <section className={styles.grid}>
          {pillars.map((pillar) => (
            <Link className={styles.panel} href={pillar.href} key={pillar.title}>
              <h2>{pillar.title}</h2>
              <p>{pillar.detail}</p>
              <span className={styles.meta}>Open workspace</span>
            </Link>
          ))}
        </section>
        <section className={styles.grid}>
          <div className={styles.panel}>
            <h2>Model Intelligence</h2>
            <p>Route a task, generate a blended answer, and self-score the result.</p>
            <div className={styles.form}>
              <textarea className={styles.textarea} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              <button className={styles.button} disabled={loading} onClick={routeModel}>Route Model</button>
              <button className={styles.button} disabled={loading} onClick={blendAnswer}>Generate Blended Answer</button>
            </div>
          </div>
          <pre className={styles.output}>
            {blendResult
              ? JSON.stringify({
                task_type: blendResult.task_type,
                selected_model: blendResult.selected_model,
                evaluation: blendResult.evaluation,
                answer: blendResult.answer,
              }, null, 2)
              : routeResult
                ? JSON.stringify(routeResult, null, 2)
                : 'Model routing and blended answer output will appear here.'}
          </pre>
        </section>
        <section className={styles.grid}>
          <div className={styles.panel}>
            <h2>Memory Transparency</h2>
            <p>Show what NEXUS currently knows and which memories can influence personalization.</p>
            <button className={styles.button} onClick={loadMemorySummary}>What does NEXUS know?</button>
          </div>
          <pre className={styles.output}>
            {memorySummary ? JSON.stringify(memorySummary, null, 2) : 'Memory summary will appear here.'}
          </pre>
        </section>
      </main>
    </AppShell>
  );
}
