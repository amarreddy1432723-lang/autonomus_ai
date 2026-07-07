'use client';

import Link from 'next/link';
import AppShell from '../../components/AppShell';
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
      </main>
    </AppShell>
  );
}
