'use client';

import { Suspense } from 'react';
import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronRight,
  Circle,
  Cloud,
  Code2,
  CreditCard,
  Database,
  Fingerprint,
  GitBranch,
  Layers3,
  LockKeyhole,
  ServerCog,
  Settings,
  Sparkles,
  UserRound,
} from 'lucide-react';
import styles from './TechnologyStack.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'done' },
  { label: 'Product Blueprint', state: 'done' },
  { label: 'Architecture Strategy', state: 'done' },
  { label: 'Technology Stack', state: 'active' },
  { label: 'Roadmap', state: 'upcoming' },
  { label: 'AI Team', state: 'upcoming' },
  { label: 'Build', state: 'upcoming' },
] as const;

const STACKS = {
  recommended: {
    name: 'Recommended Stack',
    cards: [
      { title: 'Frontend', icon: Code2, recommended: 'Next.js', reason: ['Excellent SEO', 'Server Components', 'Fast Rendering', 'Large Ecosystem'], alternatives: ['React', 'Vue', 'SvelteKit'], confidence: 98, tone: 'purple' },
      { title: 'Backend', icon: ServerCog, recommended: 'FastAPI', reason: ['Excellent AI ecosystem', 'High performance', 'Easy API development'], alternatives: ['NestJS', 'Spring Boot', 'Express'], confidence: 96, tone: 'blue' },
      { title: 'Database', icon: Database, recommended: 'PostgreSQL', reason: ['Reliable', 'Scalable', 'Open Source', 'Excellent tooling'], alternatives: ['MySQL', 'MongoDB', 'CockroachDB'], confidence: 99, tone: 'green' },
      { title: 'AI Layer', icon: Sparkles, recommended: 'Model Router', reason: ['Avoid vendor lock-in', 'Automatic routing', 'Fallback models'], alternatives: ['OpenAI', 'Claude', 'Gemini', 'Groq', 'Ollama'], confidence: 100, tone: 'purple' },
      { title: 'Infrastructure', icon: Cloud, recommended: 'Railway + Cloudflare + Docker + GitHub Actions', reason: ['Fast deploys', 'Portable runtime', 'Simple CI/CD'], alternatives: ['AWS', 'Azure', 'GCP', 'Render'], confidence: 94, tone: 'blue' },
      { title: 'Authentication', icon: Fingerprint, recommended: 'Clerk', reason: ['Enterprise ready', 'OAuth', 'Passkeys', 'Multi-device'], alternatives: ['Auth0', 'Firebase', 'Supabase Auth'], confidence: 95, tone: 'green' },
      { title: 'Payments', icon: CreditCard, recommended: 'Stripe', reason: ['Global', 'Subscriptions', 'Enterprise APIs'], alternatives: ['Razorpay', 'Paddle'], confidence: 97, tone: 'purple' },
    ],
  },
  node: {
    name: 'Node.js Stack',
    cards: [
      { title: 'Frontend', icon: Code2, recommended: 'Next.js', reason: ['Unified TypeScript', 'Strong ecosystem', 'Great DX'], alternatives: ['Remix', 'Vite React'], confidence: 95, tone: 'purple' },
      { title: 'Backend', icon: ServerCog, recommended: 'NestJS', reason: ['Structured modules', 'TypeScript', 'Enterprise patterns'], alternatives: ['Express', 'Fastify'], confidence: 91, tone: 'blue' },
      { title: 'Database', icon: Database, recommended: 'PostgreSQL', reason: ['Transactional', 'Mature', 'Great ORM support'], alternatives: ['MongoDB', 'PlanetScale'], confidence: 96, tone: 'green' },
      { title: 'AI Layer', icon: Sparkles, recommended: 'Model Router', reason: ['Provider fallback', 'Task routing', 'Cost controls'], alternatives: ['OpenAI only', 'LangChain'], confidence: 96, tone: 'purple' },
      { title: 'Infrastructure', icon: Cloud, recommended: 'Vercel + Railway', reason: ['Fast frontend deploys', 'Simple API hosting'], alternatives: ['AWS', 'Render'], confidence: 90, tone: 'blue' },
      { title: 'Authentication', icon: Fingerprint, recommended: 'Clerk', reason: ['Next.js friendly', 'Organizations', 'Billing ready'], alternatives: ['Auth0', 'NextAuth'], confidence: 94, tone: 'green' },
      { title: 'Payments', icon: CreditCard, recommended: 'Stripe', reason: ['Subscription primitives', 'Webhooks', 'Global support'], alternatives: ['Paddle'], confidence: 97, tone: 'purple' },
    ],
  },
  python: {
    name: 'Python Stack',
    cards: [
      { title: 'Frontend', icon: Code2, recommended: 'Next.js', reason: ['Polished UX', 'SEO', 'Modern routing'], alternatives: ['React', 'Vue'], confidence: 94, tone: 'purple' },
      { title: 'Backend', icon: ServerCog, recommended: 'FastAPI', reason: ['AI-native ecosystem', 'Typed APIs', 'High performance'], alternatives: ['Django', 'Flask'], confidence: 98, tone: 'blue' },
      { title: 'Database', icon: Database, recommended: 'PostgreSQL', reason: ['Reliable', 'SQLAlchemy support', 'Strong indexing'], alternatives: ['MySQL', 'MongoDB'], confidence: 99, tone: 'green' },
      { title: 'AI Layer', icon: Sparkles, recommended: 'Model Router', reason: ['Best for workers', 'Local/cloud routing', 'Evals friendly'], alternatives: ['OpenAI SDK', 'LiteLLM'], confidence: 100, tone: 'purple' },
      { title: 'Infrastructure', icon: Cloud, recommended: 'Railway + Docker', reason: ['Simple services', 'Worker friendly', 'Portable'], alternatives: ['AWS ECS', 'Render'], confidence: 94, tone: 'blue' },
      { title: 'Authentication', icon: Fingerprint, recommended: 'Clerk', reason: ['Hosted auth', 'JWTs', 'Org-ready'], alternatives: ['Auth0', 'Supabase Auth'], confidence: 95, tone: 'green' },
      { title: 'Payments', icon: CreditCard, recommended: 'Stripe', reason: ['Usage billing', 'Portal', 'Invoices'], alternatives: ['Paddle', 'Razorpay'], confidence: 97, tone: 'purple' },
    ],
  },
  enterprise: {
    name: 'Java Enterprise',
    cards: [
      { title: 'Frontend', icon: Code2, recommended: 'React + Vite', reason: ['Enterprise control', 'Flexible deployment', 'Mature'], alternatives: ['Angular', 'Next.js'], confidence: 88, tone: 'purple' },
      { title: 'Backend', icon: ServerCog, recommended: 'Spring Boot', reason: ['Enterprise maturity', 'Security ecosystem', 'Long-term support'], alternatives: ['Quarkus', 'Micronaut'], confidence: 92, tone: 'blue' },
      { title: 'Database', icon: Database, recommended: 'PostgreSQL', reason: ['Relational integrity', 'Cost control', 'Operations maturity'], alternatives: ['Oracle', 'MySQL'], confidence: 94, tone: 'green' },
      { title: 'AI Layer', icon: Sparkles, recommended: 'Model Gateway', reason: ['Strict governance', 'Auditability', 'Provider controls'], alternatives: ['Azure AI', 'Bedrock'], confidence: 89, tone: 'purple' },
      { title: 'Infrastructure', icon: Cloud, recommended: 'Kubernetes', reason: ['Enterprise standard', 'Scales teams', 'Policy control'], alternatives: ['ECS', 'OpenShift'], confidence: 86, tone: 'blue' },
      { title: 'Authentication', icon: Fingerprint, recommended: 'OIDC / SAML', reason: ['SSO', 'Enterprise compliance', 'Centralized policy'], alternatives: ['Clerk Enterprise', 'Okta'], confidence: 91, tone: 'green' },
      { title: 'Payments', icon: CreditCard, recommended: 'Stripe Enterprise', reason: ['Invoicing', 'Contracts', 'Global support'], alternatives: ['Adyen'], confidence: 90, tone: 'purple' },
    ],
  },
  serverless: {
    name: 'Serverless Stack',
    cards: [
      { title: 'Frontend', icon: Code2, recommended: 'Next.js', reason: ['Edge rendering', 'Fast iteration', 'Excellent UX'], alternatives: ['Astro', 'Remix'], confidence: 94, tone: 'purple' },
      { title: 'Backend', icon: ServerCog, recommended: 'Cloud Functions', reason: ['Event-driven', 'Low ops', 'Elastic'], alternatives: ['Lambda', 'Cloudflare Workers'], confidence: 88, tone: 'blue' },
      { title: 'Database', icon: Database, recommended: 'Neon Postgres', reason: ['Serverless Postgres', 'Branching', 'Scales down'], alternatives: ['DynamoDB', 'PlanetScale'], confidence: 90, tone: 'green' },
      { title: 'AI Layer', icon: Sparkles, recommended: 'Model Router', reason: ['Fallbacks', 'Cost routing', 'Provider freedom'], alternatives: ['OpenAI only', 'Vertex AI'], confidence: 95, tone: 'purple' },
      { title: 'Infrastructure', icon: Cloud, recommended: 'Vercel + Cloudflare', reason: ['Low operations', 'Edge delivery', 'Global reach'], alternatives: ['AWS SAM', 'Firebase'], confidence: 91, tone: 'blue' },
      { title: 'Authentication', icon: Fingerprint, recommended: 'Clerk', reason: ['Managed sessions', 'Passkeys', 'OAuth'], alternatives: ['Firebase Auth', 'Auth0'], confidence: 93, tone: 'green' },
      { title: 'Payments', icon: CreditCard, recommended: 'Stripe', reason: ['Checkout', 'Subscriptions', 'Webhooks'], alternatives: ['Paddle'], confidence: 96, tone: 'purple' },
    ],
  },
};

const SUMMARY = [
  ['Estimated Development Time', '10 Weeks'],
  ['Monthly Infrastructure Cost', '≈ $80'],
  ['AI Cost', '≈ $35/month'],
  ['Deployment Complexity', 'Low'],
  ['Maintenance', 'Easy'],
  ['Scalability', 'Excellent'],
  ['Future Migration Risk', 'Very Low'],
];

function TechnologyStackPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const [selectedStack, setSelectedStack] = useState<keyof typeof STACKS>('recommended');
  const stack = STACKS[selectedStack];

  const withIdea = (path: string) => {
    if (!idea.trim()) return path;
    return `${path}?idea=${encodeURIComponent(idea)}`;
  };

  const continueToRoadmap = () => {
    const params = new URLSearchParams();
    params.set('stage', 'roadmap');
    params.set('stack', selectedStack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/engineering-roadmap?${params.toString()}`);
  };

  const averageConfidence = useMemo(() => {
    const total = stack.cards.reduce((sum, card) => sum + card.confidence, 0);
    return Math.round(total / stack.cards.length);
  }, [stack.cards]);

  return (
    <main className={styles.stack}>
      <section className={styles.window} aria-label="Arceus Code recommended technology stack">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(withIdea('/architecture-strategy'))}>
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
            <button type="button" className={styles.iconButton} aria-label="Notifications"><Bell size={18} /></button>
            <button type="button" className={styles.iconButton} aria-label="Settings" onClick={() => router.push('/settings')}><Settings size={18} /></button>
            <button type="button" className={styles.profileButton} aria-label="Profile"><LockKeyhole size={17} /></button>
          </div>
        </header>

        <section className={styles.hero}>
          <p><GitBranch size={16} /> Principal Software Architect</p>
          <h1>Recommended Technology Stack</h1>
          <span>Arceus has evaluated multiple technologies and selected the best stack for your product.</span>
          <div className={styles.confidence}><strong>{averageConfidence}%</strong><small>Match</small></div>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.cardGrid}>
            {stack.cards.map((card, index) => {
              const Icon = card.icon;
              return (
                <article key={`${selectedStack}-${card.title}`} className={styles.techCard} data-tone={card.tone} style={{ animationDelay: `${index * 55}ms` }}>
                  <div className={styles.cardHeader}>
                    <span><Icon size={21} /></span>
                    <div>
                      <h2>{card.title}</h2>
                      <small>Recommended</small>
                      <strong>{card.recommended}</strong>
                    </div>
                  </div>
                  <div className={styles.reasonList}>
                    {card.reason.map((item) => <p key={item}><Check size={14} />{item}</p>)}
                  </div>
                  <div className={styles.alternatives}>
                    <small>Alternatives</small>
                    <div>{card.alternatives.map((item) => <b key={item}>{item}</b>)}</div>
                  </div>
                  <div className={styles.confidenceBar}>
                    <span><small>Confidence</small><strong>{card.confidence}%</strong></span>
                    <i><em style={{ width: `${card.confidence}%` }} /></i>
                  </div>
                </article>
              );
            })}
          </div>

          <aside className={styles.summary}>
            <div className={styles.summaryHeader}>
              <span><Layers3 size={20} /></span>
              <div>
                <h2>Engineering Summary</h2>
                <p>Foundation selected for speed, cost and long-term migration.</p>
              </div>
            </div>
            <div className={styles.summaryRows}>
              {SUMMARY.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
            </div>
            <details className={styles.alternativeStacks} open>
              <summary>Alternative Stacks</summary>
              <div>
                {Object.entries(STACKS).map(([key, value]) => (
                  <button key={key} type="button" data-active={selectedStack === key} onClick={() => setSelectedStack(key as keyof typeof STACKS)}>
                    {value.name}
                  </button>
                ))}
              </div>
            </details>
          </aside>
        </section>

        <div className={styles.infoBanner}>
          <span>💡</span>
          These recommendations are optimized for your product goals, engineering resources, and long-term scalability.
        </div>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push(withIdea('/architecture-strategy'))}>
            <ArrowLeft size={18} />
            Back
          </button>
          <button type="button" className={styles.secondaryButton}>Customize Stack</button>
          <button type="button" className={styles.primaryButton} onClick={continueToRoadmap}>
            Approve Technology Stack
            <ChevronRight size={18} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function TechnologyStackPage() {
  return (
    <Suspense fallback={null}>
      <TechnologyStackPageContent />
    </Suspense>
  );
}
