'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronRight,
  Circle,
  Network,
  Rocket,
  Settings,
  Sparkles,
  UserRound,
  UsersRound,
} from 'lucide-react';
import styles from './AiWorkforce.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'done' },
  { label: 'Product Blueprint', state: 'done' },
  { label: 'Architecture Strategy', state: 'done' },
  { label: 'Technology Stack', state: 'done' },
  { label: 'Engineering Roadmap', state: 'done' },
  { label: 'AI Workforce', state: 'active' },
  { label: 'Execution', state: 'upcoming' },
] as const;

const SPECIALISTS = [
  {
    icon: 'EM',
    role: 'Engineering Manager',
    status: 'Assigned',
    responsibilities: ['Coordinate roadmap', 'Review milestones', 'Approve implementation'],
    model: 'Claude',
    reason: 'Excellent planning and reasoning.',
    tone: 'purple',
  },
  {
    icon: 'SA',
    role: 'Solution Architect',
    status: 'Assigned',
    responsibilities: ['System design', 'Architecture validation', 'Scalability'],
    model: 'GPT',
    reason: 'Excellent architectural reasoning.',
    tone: 'blue',
  },
  {
    icon: 'FE',
    role: 'Frontend Engineer',
    status: 'Ready',
    responsibilities: ['React', 'Next.js', 'UI', 'Accessibility'],
    model: 'GPT',
    reason: 'Strong interface implementation and component reasoning.',
    tone: 'violet',
  },
  {
    icon: 'BE',
    role: 'Backend Engineer',
    status: 'Ready',
    responsibilities: ['FastAPI', 'Database', 'REST APIs', 'Caching'],
    model: 'Claude',
    reason: 'Reliable systems reasoning and API design.',
    tone: 'green',
  },
  {
    icon: 'DB',
    role: 'Database Engineer',
    status: 'Ready',
    responsibilities: ['Schema', 'Indexes', 'Migration', 'Optimization'],
    model: 'GPT',
    reason: 'Precise structured data and query planning.',
    tone: 'blue',
  },
  {
    icon: 'AI',
    role: 'AI Engineer',
    status: 'Assigned',
    responsibilities: ['Model Router', 'Prompt System', 'Memory', 'Agents'],
    model: 'Claude',
    reason: 'Careful agent planning and context control.',
    tone: 'purple',
  },
  {
    icon: 'SE',
    role: 'Security Engineer',
    status: 'Ready',
    responsibilities: ['Authentication', 'Encryption', 'Security Review', 'Compliance'],
    model: 'GPT',
    reason: 'Strong checklist coverage and threat modeling.',
    tone: 'orange',
  },
  {
    icon: 'QA',
    role: 'QA Engineer',
    status: 'Ready',
    responsibilities: ['Testing', 'Regression', 'Accessibility', 'Bug Detection'],
    model: 'Claude',
    reason: 'Excellent edge-case discovery and test design.',
    tone: 'green',
  },
  {
    icon: 'DO',
    role: 'DevOps Engineer',
    status: 'Ready',
    responsibilities: ['Docker', 'CI/CD', 'Deployment', 'Monitoring'],
    model: 'GPT',
    reason: 'Strong release and infrastructure execution.',
    tone: 'blue',
  },
  {
    icon: 'DE',
    role: 'Documentation Engineer',
    status: 'Ready',
    responsibilities: ['Documentation', 'Architecture Docs', 'API Docs', 'Developer Guides'],
    model: 'Claude',
    reason: 'Clear written reasoning and product explanation.',
    tone: 'violet',
  },
];

const OVERVIEW = [
  ['Total Specialists', '10'],
  ['AI Models', '4'],
  ['Parallel Teams', '3'],
  ['Estimated Build Time', '10 Weeks'],
  ['Execution Confidence', '97%'],
];

const APPROVALS = ['Architecture Approved', 'Technology Approved', 'Roadmap Approved'];

function AiWorkforcePageContent() {
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

  const launchEngineering = () => {
    const params = new URLSearchParams();
    params.set('stage', 'execution');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/executive-review?${params.toString()}`);
  };

  return (
    <main className={styles.workforce}>
      <section className={styles.window} aria-label="Arceus Code AI workforce assembly">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(withParams('/engineering-roadmap'))}>
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
            <button type="button" className={styles.profileButton} aria-label="Profile"><UserRound size={18} /></button>
          </div>
        </header>

        <section className={styles.hero}>
          <p><UsersRound size={16} /> Mission Control</p>
          <h1>Assembling Your AI Engineering Organization</h1>
          <span>Matching specialists to your project requirements.</span>
          <div className={styles.heroStats}>
            <b><small>12 Specialists Required</small>Organization sizing</b>
            <b><small>Estimated Assembly Time</small>18 seconds</b>
          </div>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.cardGrid} aria-label="Assigned AI specialists">
            {SPECIALISTS.map((specialist, index) => (
              <article
                key={specialist.role}
                className={styles.specialistCard}
                data-tone={specialist.tone}
                style={{ animationDelay: `${index * 70}ms` }}
              >
                <header>
                  <span className={styles.avatar}>{specialist.icon}</span>
                  <div>
                    <h2>{specialist.role}</h2>
                    <p><span className={styles.statusDot} />{specialist.status}</p>
                  </div>
                </header>
                <section>
                  <h3>Responsibilities</h3>
                  <div className={styles.responsibilities}>
                    {specialist.responsibilities.map((item) => <span key={item}>{item}</span>)}
                  </div>
                </section>
                <footer>
                  <div>
                    <small>Recommended Model</small>
                    <strong>{specialist.model}</strong>
                  </div>
                  <p>{specialist.reason}</p>
                </footer>
              </article>
            ))}
          </div>

          <aside className={styles.sidebar}>
            <section className={styles.overview}>
              <div className={styles.overviewHeader}>
                <span><Sparkles size={20} /></span>
                <div>
                  <h2>Organization Overview</h2>
                  <p>Your specialist teams are ready for execution.</p>
                </div>
              </div>
              <div className={styles.overviewRows}>
                {OVERVIEW.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
              </div>
              <div className={styles.approvals}>
                {APPROVALS.map((item) => <span key={item}><Check size={14} />{item}</span>)}
              </div>
            </section>

            <section className={styles.orgChart} aria-label="Organization chart">
              <h2><Network size={18} /> Organization Chart</h2>
              <div className={styles.chartNode}>Engineering Manager</div>
              <i />
              <div className={styles.chartNode}>Solution Architect</div>
              <i />
              <div className={styles.teamRow}>
                <span>Frontend</span>
                <span>Backend</span>
                <span>Database</span>
                <span>AI</span>
              </div>
              <i />
              <div className={styles.chartNode}>QA</div>
              <i />
              <div className={styles.chartNode}>DevOps</div>
              <i />
              <div className={styles.chartNode}>Documentation</div>
            </section>
          </aside>
        </section>

        <section className={styles.readyMessage}>
          <p>Your AI engineering organization is ready.</p>
          <span>Specialists, models, approvals and execution paths are aligned.</span>
        </section>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push(withParams('/engineering-roadmap'))}>
            <ArrowLeft size={18} />
            Back
          </button>
          <button type="button" className={styles.secondaryButton}>Customize Workforce</button>
          <button type="button" className={styles.primaryButton} onClick={launchEngineering}>
            Launch Engineering
            <Rocket size={18} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function AiWorkforcePage() {
  return (
    <Suspense fallback={null}>
      <AiWorkforcePageContent />
    </Suspense>
  );
}
