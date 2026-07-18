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
  Clock3,
  FileCheck2,
  Flag,
  GitBranch,
  Layers3,
  Rocket,
  Settings,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import styles from './EngineeringRoadmap.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'done' },
  { label: 'Product Blueprint', state: 'done' },
  { label: 'Architecture Strategy', state: 'done' },
  { label: 'Technology Stack', state: 'done' },
  { label: 'Implementation Roadmap', state: 'active' },
  { label: 'AI Workforce', state: 'upcoming' },
  { label: 'Build', state: 'upcoming' },
] as const;

const MILESTONES = [
  {
    title: 'Foundation',
    duration: '1 Week',
    objective: 'Create the product foundation so all future work has a stable base.',
    deliverables: ['Project Initialization', 'Repository Structure', 'CI/CD', 'Authentication', 'Database'],
    dependencies: ['Approved stack', 'Repo access'],
    criteria: 'Development environment fully operational',
    tone: 'purple',
  },
  {
    title: 'Core Platform',
    duration: '2 Weeks',
    objective: 'Build the essential application shell, APIs, data model and user flows.',
    deliverables: ['Backend APIs', 'Frontend Framework', 'Database Models', 'Authentication Flow', 'Project Settings'],
    dependencies: ['Foundation complete', 'Auth keys'],
    criteria: 'Users can sign in and use core app workflows',
    tone: 'blue',
  },
  {
    title: 'Business Features',
    duration: '3 Weeks',
    objective: 'Deliver the product value that users will pay for first.',
    deliverables: ['Primary Product Features', 'Payments', 'Notifications', 'Search', 'Admin Dashboard'],
    dependencies: ['Core platform APIs', 'Stripe setup'],
    criteria: 'MVP business workflow works end-to-end',
    tone: 'green',
  },
  {
    title: 'AI Features',
    duration: '2 Weeks',
    objective: 'Add intelligent workflows that make the product meaningfully differentiated.',
    deliverables: ['AI Model Router', 'Context Engine', 'Prompt System', 'Memory', 'Autonomous Agents'],
    dependencies: ['Core data model', 'Model provider keys'],
    criteria: 'AI features produce reviewable, auditable outputs',
    tone: 'purple',
  },
  {
    title: 'Quality',
    duration: '1 Week',
    objective: 'Harden the product before launch and remove trust-breaking defects.',
    deliverables: ['Testing', 'Accessibility', 'Performance', 'Security Audit', 'Documentation'],
    dependencies: ['Feature complete MVP'],
    criteria: 'Critical checks pass and launch blockers are resolved',
    tone: 'orange',
  },
  {
    title: 'Deployment',
    duration: '1 Week',
    objective: 'Prepare production operations so the product can be released and recovered.',
    deliverables: ['Production Infrastructure', 'Monitoring', 'Logging', 'Release Pipeline', 'Backup', 'Launch Checklist'],
    dependencies: ['Quality gate passed', 'Production credentials'],
    criteria: 'Production smoke test and rollback plan are verified',
    tone: 'blue',
  },
];

const SUMMARY = [
  ['Total Tasks', '142'],
  ['Major Milestones', '6'],
  ['Estimated AI Hours', '520'],
  ['Estimated Human Review', '18 Hours'],
  ['Deployment Readiness', '95%'],
  ['Overall Risk', 'Low'],
];

const RISKS = [
  ['Payment integration delays', 'Medium', 'High', 'Use Stripe test mode early and lock webhook contracts.'],
  ['Third-party API limits', 'Low', 'Medium', 'Add provider fallbacks and usage monitoring from day one.'],
  ['Performance bottlenecks', 'Medium', 'Medium', 'Run load checks before feature freeze.'],
  ['Authentication edge cases', 'Medium', 'High', 'Test expired sessions, desktop auth and org permissions.'],
];

function EngineeringRoadmapPageContent() {
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

  const approvePlan = () => {
    const params = new URLSearchParams();
    params.set('stage', 'ai-workforce');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/ai-workforce?${params.toString()}`);
  };

  return (
    <main className={styles.roadmap}>
      <section className={styles.window} aria-label="Arceus Code engineering roadmap">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(withParams('/technology-stack'))}>
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
          <p><GitBranch size={16} /> Engineering Director</p>
          <h1>Engineering Roadmap</h1>
          <span>Arceus has transformed your vision into an executable engineering plan.</span>
          <div className={styles.heroBadges}>
            <b><small>Execution Confidence</small>96%</b>
            <b><small>Estimated Duration</small>10 Weeks</b>
          </div>
        </section>

        <section className={styles.mainGrid}>
          <article className={styles.timeline}>
            <div className={styles.timelineLine} aria-hidden="true" />
            {MILESTONES.map((milestone, index) => (
              <section key={milestone.title} className={styles.milestone} data-tone={milestone.tone} style={{ animationDelay: `${index * 90}ms` }}>
                <div className={styles.node}>
                  <span>{index + 1}</span>
                </div>
                <div className={styles.milestoneCard}>
                  <header>
                    <div>
                      <small>Milestone {index + 1}</small>
                      <h2>{milestone.title}</h2>
                    </div>
                    <b><Clock3 size={15} />{milestone.duration}</b>
                  </header>
                  <p>{milestone.objective}</p>
                  <div className={styles.detailGrid}>
                    <div>
                      <h3>Deliverables</h3>
                      <div className={styles.chips}>{milestone.deliverables.map((item) => <span key={item}>{item}</span>)}</div>
                    </div>
                    <div>
                      <h3>Dependencies</h3>
                      <div className={styles.chips}>{milestone.dependencies.map((item) => <span key={item}>{item}</span>)}</div>
                    </div>
                  </div>
                  <footer>
                    <FileCheck2 size={16} />
                    <strong>Completion Criteria</strong>
                    <span>{milestone.criteria}</span>
                  </footer>
                </div>
              </section>
            ))}
          </article>

          <aside className={styles.summary}>
            <div className={styles.summaryHeader}>
              <span><Layers3 size={20} /></span>
              <div>
                <h2>Engineering Summary</h2>
                <p>Execution plan for the approved product direction.</p>
              </div>
            </div>
            <div className={styles.summaryRows}>
              {SUMMARY.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
            </div>
            <details className={styles.risks} open>
              <summary>Potential Risks <ChevronDown size={15} /></summary>
              <div>
                {RISKS.map(([title, likelihood, impact, mitigation]) => (
                  <section key={title}>
                    <strong>{title}</strong>
                    <p><span>Likelihood {likelihood}</span><span>Impact {impact}</span></p>
                    <small>{mitigation}</small>
                  </section>
                ))}
              </div>
            </details>
          </aside>
        </section>

        <div className={styles.infoBanner}>
          <span>💡</span>
          Every milestone has been optimized to reduce engineering risk while delivering value as early as possible.
        </div>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push(withParams('/technology-stack'))}>
            <ArrowLeft size={18} />
            Back
          </button>
          <button type="button" className={styles.secondaryButton}>Customize Roadmap</button>
          <button type="button" className={styles.primaryButton} onClick={approvePlan}>
            Approve Engineering Plan
            <ChevronRight size={18} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function EngineeringRoadmapPage() {
  return (
    <Suspense fallback={null}>
      <EngineeringRoadmapPageContent />
    </Suspense>
  );
}
