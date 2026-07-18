'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  CloudLightning,
  Globe2,
  Layers3,
  Settings,
  Sparkles,
  Star,
  UserRound,
  Zap,
} from 'lucide-react';
import styles from './ArchitectureStrategy.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'done' },
  { label: 'Product Blueprint', state: 'done' },
  { label: 'Architecture Strategy', state: 'active' },
  { label: 'Technology Stack', state: 'upcoming' },
  { label: 'Roadmap', state: 'upcoming' },
  { label: 'AI Team', state: 'upcoming' },
  { label: 'Build', state: 'upcoming' },
] as const;

const ARCHITECTURES = [
  {
    name: 'Modular Monolith',
    icon: Layers3,
    recommended: true,
    description: 'A single deployable application organized into well-defined modules.',
    advantages: ['Fast development', 'Lower cost', 'Easier deployment', 'Excellent for MVPs'],
    tradeoffs: ['Limited independent scaling'],
    buildTime: '8 Weeks',
    complexity: 'Medium',
    bestFor: ['Startups', 'SaaS', 'Internal Platforms'],
    tone: 'purple',
  },
  {
    name: 'Microservices',
    icon: Globe2,
    recommended: false,
    description: 'Independent services communicating through APIs and events.',
    advantages: ['Massive scalability', 'Independent deployments', 'Team autonomy'],
    tradeoffs: ['Higher operational complexity', 'More infrastructure'],
    buildTime: '14 Weeks',
    complexity: 'High',
    bestFor: ['Enterprise', 'Large Organizations', 'Global Scale'],
    tone: 'blue',
  },
  {
    name: 'Serverless Architecture',
    icon: Zap,
    recommended: false,
    description: 'Cloud-native functions with managed infrastructure.',
    advantages: ['Pay only for usage', 'Infinite scaling', 'Fast deployment'],
    tradeoffs: ['Vendor lock-in', 'Cold starts'],
    buildTime: '9 Weeks',
    complexity: 'Medium',
    bestFor: ['AI APIs', 'Event-driven systems', 'Modern cloud applications'],
    tone: 'green',
  },
];

const COMPARISON = [
  ['Modular Monolith', 'Fast', 'Strong', 'Low', 'Easy', 'Simple', 'Strong', 'Small'],
  ['Microservices', 'Slow', 'Elite', 'High', 'Hard', 'Complex', 'Strong', 'Large'],
  ['Serverless', 'Fast', 'Elite', 'Variable', 'Medium', 'Easy', 'Good', 'Small'],
];

const COMPARISON_COLUMNS = ['Architecture', 'Development Speed', 'Scalability', 'Cost', 'Maintenance', 'Deployment', 'Security', 'Team Size'];

function badgeTone(value: string) {
  if (['Fast', 'Elite', 'Low', 'Easy', 'Simple', 'Strong', 'Small', 'Good'].includes(value)) return 'good';
  if (['Medium', 'Variable', 'Strong'].includes(value)) return 'medium';
  return 'hard';
}

function ArchitectureStrategyPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';

  const withIdea = (path: string) => {
    if (!idea.trim()) return path;
    return `${path}?idea=${encodeURIComponent(idea)}`;
  };

  const continueToWorkspace = () => {
    const params = new URLSearchParams();
    params.set('stage', 'technology-stack');
    params.set('architecture', 'modular-monolith');
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/technology-stack?${params.toString()}`);
  };

  return (
    <main className={styles.strategy}>
      <section className={styles.window} aria-label="Arceus Code architecture strategy">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(withIdea('/product-blueprint'))}>
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
            <CloudLightning size={16} />
            Chief Software Architect
          </p>
          <h1>Choose an Engineering Strategy</h1>
          <span>Every architecture has different trade-offs. Arceus recommends one based on your product goals.</span>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.architectureCards}>
            {ARCHITECTURES.map((item, index) => {
              const Icon = item.icon;
              return (
                <article key={item.name} className={styles.architectureCard} data-tone={item.tone} data-recommended={item.recommended} style={{ animationDelay: `${index * 90}ms` }}>
                  {item.recommended ? (
                    <div className={styles.recommended}>
                      <Star size={14} />
                      Recommended
                    </div>
                  ) : null}
                  <div className={styles.cardTop}>
                    <span>
                      <Icon size={24} />
                    </span>
                    <div>
                      <h2>{item.name}</h2>
                      <p>{item.description}</p>
                    </div>
                  </div>
                  <div className={styles.columns}>
                    <div>
                      <h3>Advantages</h3>
                      {item.advantages.map((advantage) => (
                        <p key={advantage} className={styles.positive}><Check size={14} />{advantage}</p>
                      ))}
                    </div>
                    <div>
                      <h3>Trade-offs</h3>
                      {item.tradeoffs.map((tradeoff) => (
                        <p key={tradeoff} className={styles.tradeoff}>• {tradeoff}</p>
                      ))}
                    </div>
                  </div>
                  <div className={styles.cardMetrics}>
                    <span><small>Estimated Build Time</small><strong>{item.buildTime}</strong></span>
                    <span><small>Complexity</small><strong>{item.complexity}</strong></span>
                  </div>
                  <div className={styles.bestFor}>
                    <small>Best For</small>
                    <div>{item.bestFor.map((value) => <b key={value}>{value}</b>)}</div>
                  </div>
                </article>
              );
            })}
          </div>

          <aside className={styles.recommendationPanel}>
            <div className={styles.panelHeader}>
              <span><Sparkles size={20} /></span>
              <div>
                <h2>Arceus Recommendation</h2>
                <p>Architecture choice optimized for this product.</p>
              </div>
            </div>
            <div className={styles.recommendationHero}>
              <small>Recommended Architecture</small>
              <strong>Modular Monolith</strong>
              <em>96% Confidence</em>
            </div>
            <div className={styles.reasoning}>
              <h3>Reasoning</h3>
              {['Fastest path to market', 'Lowest operational cost', 'Easy future migration', 'Matches your product complexity'].map((item) => (
                <p key={item}><Check size={14} />{item}</p>
              ))}
            </div>
            <details className={styles.whyNot}>
              <summary>Why not the others? <ChevronDown size={15} /></summary>
              <p>Microservices add operational weight before the product needs it. Serverless is strong for event-heavy APIs, but this product benefits from clearer domain modules first.</p>
            </details>
          </aside>
        </section>

        <section className={styles.comparisonSection}>
          <div className={styles.comparisonHeader}>
            <h2>Architecture Comparison</h2>
            <p>Clear trade-offs without unnecessary engineering noise.</p>
          </div>
          <div className={styles.comparisonGrid} style={{ gridTemplateColumns: `1.15fr repeat(${COMPARISON_COLUMNS.length - 1}, minmax(92px, 1fr))` }}>
            {COMPARISON_COLUMNS.map((column) => <strong key={column}>{column}</strong>)}
            {COMPARISON.flatMap((row) => row.map((value, index) => (
              <span key={`${row[0]}-${index}`} data-tone={index === 0 ? 'name' : badgeTone(value)}>
                {value}
              </span>
            )))}
          </div>
        </section>

        <div className={styles.infoBanner}>
          <span>💡</span>
          Good architecture decisions save months of engineering effort later.
        </div>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push(withIdea('/product-blueprint'))}>
            <ArrowLeft size={18} />
            Back to Blueprint
          </button>
          <button type="button" className={styles.secondaryButton}>
            Customize Architecture
          </button>
          <button type="button" className={styles.primaryButton} onClick={continueToWorkspace}>
            Continue
            <ChevronRight size={18} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function ArchitectureStrategyPage() {
  return (
    <Suspense fallback={null}>
      <ArchitectureStrategyPageContent />
    </Suspense>
  );
}
