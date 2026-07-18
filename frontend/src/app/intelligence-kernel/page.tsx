'use client';

import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  BrainCircuit,
  Check,
  ChevronRight,
  Cpu,
  GitBranch,
  Network,
  Sparkles,
} from 'lucide-react';
import styles from './IntelligenceKernel.module.css';

const PIPELINE = [
  'Receive Objective',
  'Understand Objective',
  'Extract Knowledge',
  'Detect Domains',
  'Research',
  'Build Knowledge Graph',
  'Create Organization',
  'Assign Specialists',
  'Generate Strategy',
  'Review',
  'Approve',
  'Execute',
  'Validate',
  'Deploy',
  'Monitor',
  'Improve',
  'Learn',
];

const ENGINES = [
  ['Mission Manager', 'Understands objective, success criteria, unknowns and deliverables.'],
  ['Domain Intelligence', 'Detects one or more professional domains.'],
  ['Research Engine', 'Finds evidence, standards, docs and uncertainties.'],
  ['Knowledge Graph', 'Links decisions, requirements, incidents and patterns.'],
  ['Memory Engine', 'Preserves durable organizational memory.'],
  ['Reasoning Engine', 'Creates alternatives and compares trade-offs.'],
  ['Planning Engine', 'Builds milestones, epics, tasks and verification gates.'],
  ['Simulation Engine', 'Forecasts risks, cost, performance and timeline.'],
  ['Review Council', 'Challenges important decisions before approval.'],
  ['Conflict Resolver', 'Documents compromise when expert views disagree.'],
  ['Execution Engine', 'Coordinates actions, verification, merge and deployment.'],
  ['Learning Engine', 'Turns outcomes into reusable patterns.'],
  ['Model Router', 'Chooses the best model for each specialist and task.'],
  ['Tool Router', 'Selects safe tools, sandboxes and integrations.'],
  ['Policy Engine', 'Applies safety, privacy, auth, billing and approval constraints.'],
  ['Meta Intelligence', 'Measures Arceus itself and proposes improvements.'],
  ['Evolution Engine', 'Improves kernel, agents, workflows, models, tools and UX.'],
];

const META = [
  'Success',
  'Failure',
  'Latency',
  'Accuracy',
  'Cost',
  'User Satisfaction',
  'Agent Performance',
  'Model Performance',
  'Tool Performance',
  'Memory Usage',
  'Communication Quality',
  'Organization Efficiency',
];

const EXECUTION = ['Mission', 'Milestone', 'Epic', 'Task', 'Subtask', 'Action', 'Verification', 'Merge', 'Deployment'];

export default function IntelligenceKernelPage() {
  const router = useRouter();

  return (
    <main className={styles.kernel}>
      <section className={styles.window} aria-label="Arceus Intelligence Kernel">
        <header className={styles.topbar}>
          <button type="button" className={styles.backButton} onClick={() => router.push('/organization-network')}>
            <ArrowLeft size={18} />
            Back
          </button>
          <strong>Arceus Intelligence Kernel v1.0</strong>
          <button type="button" className={styles.primaryMini} onClick={() => router.push('/domain-intelligence')}>
            Create Mission
            <ChevronRight size={16} />
          </button>
        </header>

        <section className={styles.hero}>
          <p><Sparkles size={16} /> AI Operating System</p>
          <h1>Arceus Intelligence Kernel</h1>
          <span>The central operating system responsible for coordinating every intelligence process inside Arceus.</span>
        </section>

        <section className={styles.bus}>
          <article className={styles.kernelCore}>
            <span><BrainCircuit size={30} /></span>
            <h2>Intelligence Kernel</h2>
            <p>Understand first. Reason second. Execute third. Improve forever.</p>
          </article>
          <div className={styles.engineGrid}>
            {ENGINES.map(([name, purpose], index) => (
              <article key={name} style={{ animationDelay: `${index * 35}ms` }}>
                <strong>{name}</strong>
                <small>{purpose}</small>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.pipeline}>
          <header>
            <div>
              <h2>Mission Pipeline</h2>
              <small>Every objective becomes an optimized, validated, executable mission.</small>
            </div>
            <Network size={22} />
          </header>
          <div>
            {PIPELINE.map((step, index) => (
              <article key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
                {index < PIPELINE.length - 1 ? <ChevronRight size={16} /> : null}
              </article>
            ))}
          </div>
        </section>

        <section className={styles.lowerGrid}>
          <article className={styles.execution}>
            <header>
              <h2>Execution Kernel</h2>
              <small>No AI directly edits production. Everything moves through reviewable execution layers.</small>
            </header>
            <div>
              {EXECUTION.map((item, index) => <span key={item}>{index + 1}. {item}</span>)}
            </div>
          </article>

          <article className={styles.meta}>
            <header>
              <h2>Meta Intelligence</h2>
              <small>Arceus observes and improves itself after every mission.</small>
            </header>
            <div>
              {META.map((metric) => <span key={metric}><Check size={13} />{metric}</span>)}
            </div>
          </article>

          <article className={styles.evolution}>
            <header>
              <h2>Evolution Engine</h2>
              <small>Mission outcomes become kernel, agent, workflow and UX improvements.</small>
            </header>
            <div>
              {['Solved', 'Measured', 'Compared', 'Learned', 'Knowledge Graph', 'Improve Organization', 'Ready for Next Mission'].map((item) => (
                <span key={item}><GitBranch size={13} />{item}</span>
              ))}
            </div>
          </article>
        </section>

        <footer className={styles.footer}>
          <button type="button"><Cpu size={17} /> Inspect Engines</button>
          <button type="button"><BrainCircuit size={17} /> Run Kernel Simulation</button>
          <button type="button" onClick={() => router.push('/organization-network')}>View Organization Network</button>
        </footer>
      </section>
    </main>
  );
}
