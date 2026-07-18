'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronRight,
  Circle,
  Download,
  FileCheck2,
  Rocket,
  Settings,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import styles from './ExecutiveReview.module.css';

const STAGES = [
  { label: 'Product Blueprint', state: 'done' },
  { label: 'Architecture', state: 'done' },
  { label: 'Technology Stack', state: 'done' },
  { label: 'Roadmap', state: 'done' },
  { label: 'Workforce', state: 'done' },
  { label: 'Planning Complete', state: 'done' },
  { label: 'Executive Review', state: 'active' },
  { label: 'Implementation', state: 'upcoming' },
] as const;

const SUMMARY_CARDS = [
  {
    title: 'Project Vision',
    icon: 'PV',
    confidence: '98%',
    items: ['Product Summary', 'Target Users', 'Business Goals', 'Expected Outcomes'],
    note: 'The product direction is clear enough to begin execution.',
    tone: 'purple',
  },
  {
    title: 'Architecture',
    icon: 'AR',
    confidence: '96%',
    items: ['Modular Monolith', 'Fastest MVP path', 'Lower operational cost', 'Future scalability path'],
    note: 'Architecture is optimized for speed, clarity and future migration.',
    tone: 'blue',
  },
  {
    title: 'Technology',
    icon: 'TS',
    confidence: '95%',
    items: ['Next.js frontend', 'FastAPI backend', 'PostgreSQL database', 'Docker + Railway deployment', 'AI model router', 'Clerk authentication'],
    note: 'Stack choices are production-friendly and founder-speed appropriate.',
    tone: 'green',
  },
  {
    title: 'Execution Plan',
    icon: 'EP',
    confidence: '97%',
    items: ['6 milestones', '10 week estimate', 'Critical dependencies mapped', 'Risks mitigated'],
    note: 'The roadmap is sequenced to reduce engineering risk.',
    tone: 'orange',
  },
  {
    title: 'AI Organization',
    icon: 'AI',
    confidence: '97%',
    items: ['10 assigned specialists', '3 parallel teams', 'Review team active', 'Deployment team ready'],
    note: 'The AI workforce is aligned to architecture, stack and roadmap.',
    tone: 'purple',
  },
];

const EXECUTIVE_METRICS = [
  ['Project Readiness', '98%'],
  ['Planning Complete', '100%'],
  ['Architecture Confidence', '96%'],
  ['Engineering Risk', 'Low'],
  ['Estimated Cost', '$240'],
  ['Expected Delivery', '10 Weeks'],
];

const DECISIONS = [
  'Repository Structure',
  'Database Schema',
  'Authentication',
  'Deployment Strategy',
  'Testing Strategy',
  'AI Model Routing',
];

function ExecutiveReviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const stack = searchParams.get('stack') || 'recommended';

  const withParams = (path: string) => {
    const params = new URLSearchParams();
    if (idea.trim()) params.set('idea', idea.trim());
    if (stack) params.set('stack', stack);
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  };

  const beginImplementation = () => {
    const params = new URLSearchParams();
    params.set('stage', 'implementation');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/mission-control?${params.toString()}`);
  };

  return (
    <main className={styles.review}>
      <section className={styles.window} aria-label="Arceus Code executive engineering review">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(withParams('/ai-workforce'))}>
              <ArrowLeft size={18} />
              Back
            </button>
            <strong>Arceus Code</strong>
          </div>

          <nav className={styles.progress} aria-label="Executive review progress">
            {STAGES.map((stage, index) => (
              <span key={stage.label} className={styles.stage} data-state={stage.state}>
                {stage.state === 'done' ? <Check size={13} /> : stage.state === 'active' ? <span className={styles.activeDot} /> : <Circle size={9} />}
                {stage.label}
                {index < STAGES.length - 1 ? <ChevronRight size={13} /> : null}
              </span>
            ))}
          </nav>

          <div className={styles.rightNav}>
            <button type="button" className={styles.iconButton} aria-label="Notifications"><Bell size={18} /></button>
            <button type="button" className={styles.iconButton} aria-label="Settings" onClick={() => router.push('/settings')}><Settings size={18} /></button>
            <button type="button" className={styles.profileButton} aria-label="Profile"><UserRound size={18} /></button>
          </div>
        </header>

        <section className={styles.hero}>
          <p><FileCheck2 size={16} /> Executive Engineering Review</p>
          <h1>Engineering Review</h1>
          <span>Our engineering organization has completed planning and is ready to begin implementation.</span>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.cardGrid}>
            {SUMMARY_CARDS.map((card, index) => (
              <article key={card.title} className={styles.summaryCard} data-tone={card.tone} style={{ animationDelay: `${index * 90}ms` }}>
                <header>
                  <span>{card.icon}</span>
                  <div>
                    <h2>{card.title}</h2>
                    <small>Confidence {card.confidence}</small>
                  </div>
                </header>
                <div className={styles.itemList}>
                  {card.items.map((item) => <b key={item}><Check size={14} />{item}</b>)}
                </div>
                <p>{card.note}</p>
              </article>
            ))}
          </div>

          <aside className={styles.sidebar}>
            <section className={styles.executiveSummary}>
              <div className={styles.sidebarHeader}>
                <span><ShieldCheck size={21} /></span>
                <div>
                  <h2>Executive Summary</h2>
                  <p>Implementation readiness for founder approval.</p>
                </div>
              </div>
              <div className={styles.metricRows}>
                {EXECUTIVE_METRICS.map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            </section>
          </aside>
        </section>

        <section className={styles.decisions}>
          <div className={styles.decisionsHeader}>
            <div>
              <h2>Engineering Decisions</h2>
              <p>Everything required for implementation has been prepared.</p>
            </div>
            <span>All decisions ready</span>
          </div>
          <div className={styles.decisionGrid}>
            {DECISIONS.map((decision, index) => (
              <article key={decision} className={styles.decisionCard} style={{ animationDelay: `${index * 70}ms` }}>
                <span><Check size={16} /></span>
                <div>
                  <strong>{decision}</strong>
                  <small>Ready</small>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.banner}>
          <strong>The engineering organization is ready to begin implementation.</strong>
        </section>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton}>Modify Plan</button>
          <button type="button" className={styles.secondaryButton}>
            <Download size={18} />
            Download Engineering Report
          </button>
          <button type="button" className={styles.primaryButton} onClick={beginImplementation}>
            <Rocket size={18} />
            Begin Implementation
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function ExecutiveReviewPage() {
  return (
    <Suspense fallback={null}>
      <ExecutiveReviewPageContent />
    </Suspense>
  );
}
