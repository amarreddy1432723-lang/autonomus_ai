'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Brain,
  Check,
  ChevronRight,
  Clock3,
  GitBranch,
  History,
  Network,
  Search,
  Sparkles,
} from 'lucide-react';
import styles from './KnowledgeGraph.module.css';

const CATEGORIES = [
  'Architecture',
  'Features',
  'Code',
  'Testing',
  'Deployments',
  'Incidents',
  'Customers',
  'Security',
  'Performance',
  'AI Decisions',
  'Meetings',
  'Design',
  'Documentation',
  'Roadmap',
];

const NODES = [
  { label: 'Product Vision', x: 48, y: 12, tone: 'purple' },
  { label: 'Architecture', x: 50, y: 27, tone: 'blue' },
  { label: 'Authentication', x: 34, y: 43, tone: 'green', active: true },
  { label: 'OAuth', x: 54, y: 49, tone: 'purple' },
  { label: 'Security Review', x: 70, y: 40, tone: 'orange' },
  { label: 'Deployment', x: 62, y: 64, tone: 'blue' },
  { label: 'Customer Feedback', x: 36, y: 68, tone: 'green' },
  { label: 'Version 2.0', x: 50, y: 82, tone: 'purple' },
];

const MEMORY = [
  ['First architecture', 'Modular monolith approved'],
  ['Last deployment', 'Production v1.0.0 healthy'],
  ['Current roadmap', 'Collaboration and offline mode'],
  ['Technical debt', 'Auth edge cases and test coverage'],
  ['Pending improvements', 'Passkeys, localization, image loading'],
  ['Business goals', 'Team adoption and paid conversion'],
  ['Team preferences', 'Small patches, strong rollback'],
  ['Coding standards', 'Typed APIs, receipt-first work'],
  ['Known risks', 'Provider limits and OAuth config'],
];

const DETAILS = [
  'Why it was chosen',
  'Who suggested it',
  'Alternative approaches',
  'Related pull requests',
  'Related documentation',
  'Related bugs',
  'Related deployments',
  'Related conversations',
  'Future improvements',
];

const TIMELINE = [
  'Project Creation',
  'Architecture Review',
  'Sprint 1',
  'Deployment',
  'Production',
  'Incident',
  'Optimization',
  'Version 2',
];

function KnowledgeGraphPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const stack = searchParams.get('stack') || 'recommended';

  const openWorkspace = () => {
    const params = new URLSearchParams();
    params.set('stage', 'knowledge');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/workspace?${params.toString()}`);
  };

  return (
    <main className={styles.knowledge}>
      <section className={styles.window} aria-label="Arceus Code engineering knowledge graph">
        <header className={styles.hero}>
          <p><span /> Learning Continuously</p>
          <h1>Engineering Knowledge Graph</h1>
          <strong>Every decision your engineering organization has ever made.</strong>
        </header>

        <section className={styles.workspace}>
          <aside className={styles.leftPanel}>
            <div className={styles.panelHeader}>
              <h2>Categories</h2>
              <small>Search, filter and timeline by domain.</small>
            </div>
            <label className={styles.searchBox}>
              <Search size={16} />
              <input aria-label="Search knowledge categories" placeholder="Search knowledge..." />
            </label>
            <div className={styles.categoryList}>
              {CATEGORIES.map((category, index) => (
                <button type="button" key={category} className={index === 0 ? styles.activeCategory : ''}>
                  <span>{category.slice(0, 2).toUpperCase()}</span>
                  {category}
                </button>
              ))}
            </div>
          </aside>

          <section className={styles.graphPanel}>
            <div className={styles.panelHeader}>
              <div>
                <h2>Interactive Knowledge Graph</h2>
                <small>Click a node to reveal why decisions were made and what they connect to.</small>
              </div>
              <b><Network size={16} /> 428 memories linked</b>
            </div>

            <div className={styles.graphCanvas} aria-label="Connected engineering decisions">
              <svg className={styles.connections} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <path d="M48 12 C48 18, 50 20, 50 27" />
                <path d="M50 27 C44 34, 38 36, 34 43" />
                <path d="M50 27 C55 35, 54 41, 54 49" />
                <path d="M54 49 C61 46, 66 43, 70 40" />
                <path d="M70 40 C70 52, 66 58, 62 64" />
                <path d="M34 43 C32 54, 34 62, 36 68" />
                <path d="M36 68 C42 76, 48 80, 50 82" />
                <path d="M62 64 C58 72, 54 78, 50 82" />
              </svg>
              {NODES.map((node, index) => (
                <button
                  type="button"
                  key={node.label}
                  className={`${styles.node} ${node.active ? styles.activeNode : ''}`}
                  data-tone={node.tone}
                  style={{ left: `${node.x}%`, top: `${node.y}%`, animationDelay: `${index * 80}ms` }}
                >
                  <span>{node.label}</span>
                </button>
              ))}
            </div>

            <article className={styles.contextCard}>
              <div>
                <span><Brain size={20} /></span>
                <div>
                  <h3>Authentication</h3>
                  <small>Selected context with connected evidence.</small>
                </div>
              </div>
              <div className={styles.detailGrid}>
                {DETAILS.map((item) => <b key={item}><Check size={14} />{item}</b>)}
              </div>
            </article>
          </section>

          <aside className={styles.rightPanel}>
            <div className={styles.panelHeader}>
              <h2>AI Memory</h2>
              <small>Arceus remembers the organization.</small>
            </div>
            <div className={styles.memoryList}>
              {MEMORY.map(([label, value]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </article>
              ))}
            </div>
          </aside>
        </section>

        <section className={styles.timeMachine}>
          <header>
            <div>
              <h2>Time Machine</h2>
              <small>Restore historical context from any point in the product lifecycle.</small>
            </div>
            <Clock3 size={20} />
          </header>
          <div>
            {TIMELINE.map((point, index) => (
              <article key={point}>
                <span>{index + 1}</span>
                <strong>{point}</strong>
                {index < TIMELINE.length - 1 ? <ChevronRight size={18} /> : null}
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.footer}>
          <button type="button"><Search size={17} /> Search Knowledge</button>
          <button type="button"><Sparkles size={17} /> Ask Engineering Memory</button>
          <button type="button"><GitBranch size={17} /> Compare Decisions</button>
          <button type="button" onClick={openWorkspace}><History size={17} /> Restore Context</button>
        </footer>
      </section>
    </main>
  );
}

export default function KnowledgeGraphPage() {
  return (
    <Suspense fallback={null}>
      <KnowledgeGraphPageContent />
    </Suspense>
  );
}
