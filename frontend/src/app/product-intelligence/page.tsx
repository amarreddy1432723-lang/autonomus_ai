'use client';

import { Suspense } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  Loader2,
  Save,
  Settings,
  Sparkles,
  UserRound,
} from 'lucide-react';
import styles from './ProductIntelligence.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'active' },
  { label: 'Blueprint', state: 'upcoming' },
  { label: 'Architecture', state: 'upcoming' },
  { label: 'AI Team', state: 'upcoming' },
  { label: 'Build', state: 'upcoming' },
] as const;

const TASKS = [
  'Reading your requirements',
  'Understanding business goals',
  'Detecting missing features',
  'Identifying target users',
  'Researching similar products',
  'Estimating complexity',
  'Detecting technical risks',
  'Identifying security concerns',
  'Planning scalability',
  'Finding missing workflows',
  'Suggesting improvements',
  'Choosing technology candidates',
  'Preparing product blueprint',
];

const INTELLIGENCE_CARDS = [
  { label: 'Business Confidence', value: '91%', tone: 'green' },
  { label: 'Technical Confidence', value: '94%', tone: 'green' },
  { label: 'Requirement Completeness', value: '82%', tone: 'blue' },
  { label: 'Estimated MVP', value: '8 Weeks', tone: 'purple' },
  { label: 'Architecture Complexity', value: 'Medium', tone: 'orange' },
  { label: 'Deployment Difficulty', value: 'Low', tone: 'green' },
  { label: 'Overall Product Score', value: '89/100', tone: 'purple' },
];

const ROTATING_MESSAGES = [
  'Checking architecture...',
  'Finding missing requirements...',
  'Analyzing competitors...',
  'Evaluating scalability...',
  'Preparing recommendations...',
];

function taskState(index: number, activeIndex: number, complete: boolean) {
  if (complete || index < activeIndex) return 'completed';
  if (index === activeIndex) return 'thinking';
  return 'queued';
}

function taskEta(index: number, activeIndex: number, complete: boolean) {
  if (complete || index < activeIndex) return 'Complete';
  if (index === activeIndex) return 'Thinking...';
  return `${Math.max(1, index - activeIndex + 1)} min`;
}

function ProductIntelligencePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const [activeIndex, setActiveIndex] = useState(0);
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveIndex((current) => Math.min(TASKS.length, current + 1));
    }, 760);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setMessageIndex((current) => (current + 1) % ROTATING_MESSAGES.length);
    }, 1300);
    return () => window.clearInterval(timer);
  }, []);

  const complete = activeIndex >= TASKS.length;
  const summary = useMemo(() => {
    if (!idea.trim()) return 'Arceus is researching your idea before making engineering decisions.';
    const clipped = idea.trim().length > 142 ? `${idea.trim().slice(0, 142)}...` : idea.trim();
    return `Arceus is researching: “${clipped}”`;
  }, [idea]);

  const continueToBlueprint = () => {
    const params = new URLSearchParams();
    params.set('stage', 'product-blueprint');
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/product-blueprint?${params.toString()}`);
  };

  return (
    <main className={styles.intelligence}>
      <section className={styles.window} aria-label="Arceus Code product intelligence analysis">
        <div className={styles.particles} aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>

        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push('/idea-discovery')}>
              <ArrowLeft size={18} />
              Back
            </button>
            <strong>Arceus Code</strong>
          </div>

          <nav className={styles.progress} aria-label="Product build progress">
            {STAGES.map((stage, index) => (
              <span key={stage.label} className={styles.stage} data-state={stage.state}>
                {stage.state === 'done' ? <Check size={13} /> : stage.state === 'active' ? <span className={styles.activeDot} /> : <Circle size={9} />}
                {stage.label}
                {index < STAGES.length - 1 ? <ChevronRight size={13} /> : null}
              </span>
            ))}
          </nav>

          <div className={styles.rightNav}>
            <button type="button" className={styles.saveButton}>
              <Save size={16} />
              Save
            </button>
            <button type="button" className={styles.iconButton} aria-label="Notifications">
              <Bell size={18} />
            </button>
            <button type="button" className={styles.iconButton} aria-label="Settings" onClick={() => router.push('/settings')}>
              <Settings size={18} />
            </button>
            <button type="button" className={styles.profileButton} aria-label="Profile">
              <UserRound size={18} />
            </button>
          </div>
        </header>

        <section className={styles.hero}>
          <p>
            <Sparkles size={16} />
            Product Intelligence
          </p>
          <h1>Understanding Your Product</h1>
          <span>{summary}</span>
        </section>

        <section className={styles.contentGrid}>
          <article className={styles.timelineCard}>
            <div className={styles.timelineLine} aria-hidden="true" />
            {TASKS.map((task, index) => {
              const state = taskState(index, activeIndex, complete);
              return (
                <div key={task} className={styles.timelineRow} data-state={state}>
                  <span className={styles.taskIcon}>
                    {state === 'completed' ? <Check size={15} /> : state === 'thinking' ? <Loader2 size={15} /> : <Clock3 size={15} />}
                  </span>
                  <strong>{task}</strong>
                  <em>{state === 'completed' ? 'Completed' : state === 'thinking' ? 'Thinking...' : 'Queued'}</em>
                  <small>{taskEta(index, activeIndex, complete)}</small>
                </div>
              );
            })}
          </article>

          <aside className={styles.livePanel}>
            <div className={styles.panelHeader}>
              <h2>Live Intelligence</h2>
              <p>Product signals updated as Arceus reasons.</p>
            </div>
            <div className={styles.scoreGrid}>
              {INTELLIGENCE_CARDS.map((card, index) => (
                <div key={card.label} className={styles.scoreCard} data-tone={card.tone} style={{ animationDelay: `${index * 70}ms` }}>
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <footer className={styles.footer}>
          <div className={styles.statusText}>
            <strong>{complete ? 'Your product intelligence brief is ready.' : 'Our engineering organization is analyzing your vision.'}</strong>
            <span>{complete ? 'Blueprint recommendations are prepared.' : ROTATING_MESSAGES[messageIndex]}</span>
          </div>
          <div className={styles.footerButtons}>
            <button type="button" className={styles.primaryButton} disabled={!complete} onClick={continueToBlueprint}>
              Continue
              <ChevronRight size={18} />
            </button>
            <button type="button" className={styles.secondaryButton} disabled={!complete}>
              View Details
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}

export default function ProductIntelligencePage() {
  return (
    <Suspense fallback={null}>
      <ProductIntelligencePageContent />
    </Suspense>
  );
}
