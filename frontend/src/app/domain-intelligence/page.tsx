'use client';

import { Suspense } from 'react';
import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Check,
  ChevronRight,
  Circle,
  FlaskConical,
  Network,
  Settings,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import styles from './DomainIntelligence.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Domain Intelligence', state: 'active' },
  { label: 'Product Intelligence', state: 'upcoming' },
  { label: 'Blueprint', state: 'upcoming' },
  { label: 'Architecture', state: 'upcoming' },
  { label: 'AI Organization', state: 'upcoming' },
] as const;

const DOMAINS = [
  {
    name: 'Software Engineering',
    confidence: '96%',
    summary: 'Full-stack product delivery, architecture, code review, testing and release execution.',
    specialists: ['Engineering Manager', 'Solution Architect', 'Frontend', 'Backend', 'QA', 'DevOps'],
    tone: 'purple',
  },
  {
    name: 'Cyber Security',
    confidence: '91%',
    summary: 'Threat modeling, secure reviews, compliance mapping and safe validation workflows.',
    specialists: ['CISO', 'Security Architect', 'AppSec', 'Cloud Security', 'Incident Response'],
    tone: 'orange',
  },
  {
    name: 'AI & Machine Learning',
    confidence: '89%',
    summary: 'Model selection, RAG, evaluation, cost control, safety and agent architecture.',
    specialists: ['Chief AI Scientist', 'LLM Engineer', 'Evaluation Engineer', 'MLOps', 'Safety Engineer'],
    tone: 'blue',
  },
  {
    name: 'Healthcare',
    confidence: '82%',
    summary: 'FHIR, privacy, clinical workflows, medical data, compliance and security-first delivery.',
    specialists: ['Healthcare Architect', 'FHIR Specialist', 'Privacy', 'Clinical Workflow', 'Security'],
    tone: 'green',
  },
  {
    name: 'Finance',
    confidence: '78%',
    summary: 'Payments, fraud, risk, reporting, regulatory constraints and secure transaction design.',
    specialists: ['FinTech Architect', 'Payments', 'Risk', 'Fraud Detection', 'Compliance'],
    tone: 'purple',
  },
  {
    name: 'Cloud Infrastructure',
    confidence: '74%',
    summary: 'Kubernetes, reliability, observability, disaster recovery and infrastructure cost control.',
    specialists: ['Cloud CTO', 'Platform Engineer', 'SRE', 'Observability', 'FinOps'],
    tone: 'blue',
  },
];

const PIPELINE = [
  'Understand the Problem',
  'Classify the Domain',
  'Identify Missing Information',
  'Perform Deep Research',
  'Generate Multiple Strategies',
  'Compare Trade-offs',
  'Select Optimal Strategy',
  'Create Roadmap',
  'Assemble AI Organization',
  'Execute, Validate and Improve',
];

const RECOMMENDATIONS = [
  'Explain why before implementation',
  'Compare alternatives and trade-offs',
  'Track risks, cost and scalability',
  'Document every decision',
  'Continuously improve after release',
];

function DomainIntelligencePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const selectedDomain = useMemo(() => {
    const lower = idea.toLowerCase();
    if (lower.includes('health') || lower.includes('clinic') || lower.includes('medical')) return 'Healthcare';
    if (lower.includes('security') || lower.includes('threat') || lower.includes('compliance')) return 'Cyber Security';
    if (lower.includes('model') || lower.includes('llm') || lower.includes('machine learning') || lower.includes('ai')) return 'AI & Machine Learning';
    if (lower.includes('payment') || lower.includes('finance') || lower.includes('bank')) return 'Finance';
    if (lower.includes('cloud') || lower.includes('kubernetes') || lower.includes('infra')) return 'Cloud Infrastructure';
    return 'Software Engineering';
  }, [idea]);

  const continueFlow = () => {
    const params = new URLSearchParams();
    params.set('stage', 'product-intelligence');
    params.set('domain', selectedDomain);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/product-intelligence?${params.toString()}`);
  };

  return (
    <main className={styles.domain}>
      <section className={styles.window} aria-label="Arceus Code domain intelligence engine">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push('/idea-discovery')}>
              <ArrowLeft size={18} />
              Back
            </button>
            <strong>Arceus Code</strong>
          </div>

          <nav className={styles.progress} aria-label="Domain intelligence progress">
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
          <p><Sparkles size={16} /> Arceus Intelligence Core</p>
          <h1>Dynamic Domain Intelligence</h1>
          <span>Arceus is identifying the right engineering organization for your problem.</span>
        </section>

        <section className={styles.mainGrid}>
          <article className={styles.domainPanel}>
            <header>
              <div>
                <h2>Detected Domains</h2>
                <small>Arceus never uses a fixed workflow. It classifies the work first.</small>
              </div>
              <b><Network size={16} /> Selected: {selectedDomain}</b>
            </header>
            <div className={styles.domainGrid}>
              {DOMAINS.map((domain, index) => (
                <section
                  key={domain.name}
                  className={`${styles.domainCard} ${domain.name === selectedDomain ? styles.selectedCard : ''}`}
                  data-tone={domain.tone}
                  style={{ animationDelay: `${index * 70}ms` }}
                >
                  <div>
                    <h3>{domain.name}</h3>
                    <span>{domain.confidence}</span>
                  </div>
                  <p>{domain.summary}</p>
                  <div>
                    {domain.specialists.map((specialist) => <b key={specialist}>{specialist}</b>)}
                  </div>
                </section>
              ))}
            </div>
          </article>

          <aside className={styles.sidebar}>
            <section className={styles.pipeline}>
              <div className={styles.sidebarHeader}>
                <span><FlaskConical size={20} /></span>
                <div>
                  <h2>Reasoning Pipeline</h2>
                  <p>Every specialist follows this professional process.</p>
                </div>
              </div>
              <div>
                {PIPELINE.map((step, index) => (
                  <article key={step}>
                    <span>{index + 1}</span>
                    <strong>{step}</strong>
                  </article>
                ))}
              </div>
            </section>

            <section className={styles.principles}>
              <h2><ShieldCheck size={18} /> Recommendation Standard</h2>
              {RECOMMENDATIONS.map((item) => <p key={item}><Check size={14} />{item}</p>)}
            </section>
          </aside>
        </section>

        <footer className={styles.footer}>
          <p>Arceus will assemble Staff-level domain specialists before planning or implementation.</p>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push('/organization-network')}>
            View Organization Network
          </button>
          <button type="button" className={styles.primaryButton} onClick={continueFlow}>
            Continue with {selectedDomain}
            <ChevronRight size={18} />
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function DomainIntelligencePage() {
  return (
    <Suspense fallback={null}>
      <DomainIntelligencePageContent />
    </Suspense>
  );
}
