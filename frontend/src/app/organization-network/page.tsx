'use client';

import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Brain,
  Check,
  ChevronRight,
  GitBranch,
  MessagesSquare,
  Network,
  Sparkles,
} from 'lucide-react';
import styles from './OrganizationNetwork.module.css';

const NETWORK_LAYERS = [
  ['User Objective', 'The founder states what must be solved.'],
  ['Arceus Core AI', 'CEO + intelligence layer understands mission and constraints.'],
  ['Domain Intelligence', 'Detects software, security, healthcare, cloud, finance and other domains.'],
  ['Dynamic Organization Builder', 'Creates specialists unique to the mission.'],
  ['AI Organization Network', 'CEO, CTO, product, research, security, legal, medical, cloud, QA and more.'],
  ['Shared Organizational Memory', 'Requirements, risks, research, code, tests, incidents and roadmap.'],
  ['Multi-Agent Collaboration Bus', 'Structured messages, debate, review, challenge and verification.'],
  ['Execution + Continuous Learning', 'Milestones, tasks, monitoring, outcomes, lessons and reusable patterns.'],
];

const REVIEW_COUNCIL = [
  'Architecture',
  'Security',
  'Performance',
  'Accessibility',
  'Compliance',
  'Reliability',
  'Cost',
  'Scalability',
  'Maintainability',
  'Business',
  'UX',
  'Future Evolution',
];

const MESSAGE_FIELDS = [
  ['from', 'Security Engineer'],
  ['to', 'Backend Engineer'],
  ['topic', 'Authentication Review'],
  ['priority', 'High'],
  ['finding', 'Refresh tokens should rotate on every use.'],
  ['confidence', '0.97'],
  ['status', 'Needs Review'],
];

const GENERATIONS = [
  ['Generation 1', 'Single orchestrator + 5 specialists + shared memory.'],
  ['Generation 2', 'Dynamic teams + knowledge graph + review council.'],
  ['Generation 3', 'Cross-domain organizations for software, AI, security, healthcare, finance and cloud.'],
  ['Generation 4', 'Autonomous planning, execution, monitoring and improvement with human approvals.'],
  ['Generation 5', 'True Artificial Engineering Organization coordinating hundreds of specialists.'],
];

export default function OrganizationNetworkPage() {
  const router = useRouter();

  return (
    <main className={styles.networkPage}>
      <section className={styles.window} aria-label="Arceus artificial engineering organization network">
        <header className={styles.topbar}>
          <button type="button" onClick={() => router.push('/domain-intelligence')} className={styles.backButton}>
            <ArrowLeft size={18} />
            Back
          </button>
          <strong>Arceus Constitution v1.0</strong>
          <button type="button" className={styles.primaryMini} onClick={() => router.push('/launch')}>
            Start Mission
            <ChevronRight size={16} />
          </button>
        </header>

        <section className={styles.hero}>
          <p><Sparkles size={16} /> Artificial Engineering Organization</p>
          <h1>Arceus Organization Network</h1>
          <span>Not a chatbot. Not a single coding model. A living professional organization with memory, review, execution and learning.</span>
        </section>

        <section className={styles.mainGrid}>
          <article className={styles.flowPanel}>
            <header>
              <h2>Operating Model</h2>
              <small>User objective becomes a reviewed, executable and improving mission.</small>
            </header>
            <div className={styles.flow}>
              {NETWORK_LAYERS.map(([title, detail], index) => (
                <section key={title} className={styles.flowNode} style={{ animationDelay: `${index * 70}ms` }}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </div>
                  {index < NETWORK_LAYERS.length - 1 ? <ChevronRight size={18} /> : null}
                </section>
              ))}
            </div>
          </article>

          <aside className={styles.sideStack}>
            <section className={styles.messagePanel}>
              <div className={styles.panelTitle}>
                <span><MessagesSquare size={20} /></span>
                <div>
                  <h2>Specialist Message</h2>
                  <p>Structured collaboration, not loose prompts.</p>
                </div>
              </div>
              <div className={styles.messageFields}>
                {MESSAGE_FIELDS.map(([field, value]) => (
                  <article key={field}>
                    <small>{field}</small>
                    <strong>{value}</strong>
                  </article>
                ))}
              </div>
            </section>

            <section className={styles.reviewPanel}>
              <h2><Check size={18} /> Universal Review Council</h2>
              <div>
                {REVIEW_COUNCIL.map((lens) => <span key={lens}>{lens}</span>)}
              </div>
            </section>
          </aside>
        </section>

        <section className={styles.generationPanel}>
          <header>
            <div>
              <h2>Five Generations of Arceus</h2>
              <small>The roadmap from orchestrated specialists to a true Artificial Engineering Organization.</small>
            </div>
            <Network size={22} />
          </header>
          <div>
            {GENERATIONS.map(([name, detail], index) => (
              <article key={name}>
                <span>{index + 1}</span>
                <strong>{name}</strong>
                <small>{detail}</small>
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.footer}>
          <button type="button"><Brain size={17} /> Ask Arceus Core</button>
          <button type="button"><MessagesSquare size={17} /> Open Collaboration Bus</button>
          <button type="button" onClick={() => router.push('/intelligence-kernel')}><GitBranch size={17} /> View Kernel</button>
        </footer>
      </section>
    </main>
  );
}
