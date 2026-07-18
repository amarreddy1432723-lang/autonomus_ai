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
  Edit3,
  Rocket,
  Settings,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
  UserRound,
  Users,
  WalletCards,
  WandSparkles,
} from 'lucide-react';
import styles from './ProductBlueprint.module.css';

const STAGES = [
  { label: 'Idea Discovery', state: 'done' },
  { label: 'Product Intelligence', state: 'done' },
  { label: 'Product Blueprint', state: 'active' },
  { label: 'Architecture', state: 'upcoming' },
  { label: 'Roadmap', state: 'upcoming' },
  { label: 'AI Team', state: 'upcoming' },
  { label: 'Build', state: 'upcoming' },
] as const;

const BLUEPRINT_CARDS = [
  {
    title: 'Problem',
    icon: Target,
    tone: 'purple',
    body: ['Small businesses struggle to manage appointments, payments and customer communication from one place.'],
  },
  {
    title: 'Target Users',
    icon: Users,
    tone: 'blue',
    chips: ['Business Owners', 'Customers', 'Administrators', 'Partners'],
  },
  {
    title: 'Core Features',
    icon: Sparkles,
    tone: 'purple',
    chips: ['Appointment Booking', 'Payments', 'Notifications', 'Analytics', 'Reviews', 'Customer Profiles', 'AI Assistant'],
  },
  {
    title: 'MVP',
    icon: Rocket,
    tone: 'green',
    eyebrow: 'Version 1',
    chips: ['Authentication', 'Dashboard', 'Booking', 'Payments', 'Basic Admin'],
  },
  {
    title: 'Future Features',
    icon: TrendingUp,
    tone: 'blue',
    chips: ['Marketplace', 'AI Recommendations', 'Automation', 'Enterprise Dashboard', 'API Platform'],
  },
  {
    title: 'Monetization',
    icon: WalletCards,
    tone: 'green',
    chips: ['Subscription', 'Commission', 'Marketplace Revenue', 'Enterprise License'],
  },
  {
    title: 'Risks',
    icon: TriangleAlert,
    tone: 'orange',
    chips: ['Scalability', 'Payment Compliance', 'Spam', 'Security', 'Legal'],
  },
  {
    title: 'Security',
    icon: Shield,
    tone: 'purple',
    chips: ['Role Based Access', 'Encrypted Storage', 'Audit Logs', 'Secure Authentication', 'Rate Limiting'],
  },
];

const INSIGHTS = [
  ['Overall Product Score', '92/100'],
  ['Estimated Development', '10 Weeks'],
  ['Difficulty', 'Medium'],
  ['Scalability', 'Excellent'],
  ['Business Potential', 'High'],
  ['Technical Risk', 'Low'],
  ['Recommended Architecture', 'Modular Monolith'],
];

function ProductBlueprintPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';

  const continueToArchitecture = () => {
    const params = new URLSearchParams();
    params.set('stage', 'architecture-strategy');
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/architecture-strategy?${params.toString()}`);
  };

  return (
    <main className={styles.blueprint}>
      <section className={styles.window} aria-label="Arceus Code product blueprint">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push(`/product-intelligence${idea ? `?idea=${encodeURIComponent(idea)}` : ''}`)}>
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
            <WandSparkles size={16} />
            Generated Blueprint
          </p>
          <h1>Product Blueprint</h1>
          <span>This is the product Arceus understands.</span>
          <div className={styles.confidence}>
            <small>Understanding Confidence</small>
            <strong>94%</strong>
          </div>
        </section>

        <section className={styles.mainGrid}>
          <div className={styles.cardGrid}>
            {BLUEPRINT_CARDS.map((card, index) => {
              const Icon = card.icon;
              return (
                <article key={card.title} className={styles.blueprintCard} data-tone={card.tone} style={{ animationDelay: `${index * 55}ms` }}>
                  <div className={styles.cardTitle}>
                    <span>
                      <Icon size={20} />
                    </span>
                    <h2>{card.title}</h2>
                  </div>
                  {'eyebrow' in card && card.eyebrow ? <b>{card.eyebrow}</b> : null}
                  {card.body ? card.body.map((line) => <p key={line}>{line}</p>) : null}
                  {card.chips ? (
                    <div className={styles.chips}>
                      {card.chips.map((chip) => <span key={chip}>{chip}</span>)}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>

          <aside className={styles.insights}>
            <div className={styles.insightsHeader}>
              <span>
                <Sparkles size={20} />
              </span>
              <div>
                <h2>AI Insights</h2>
                <p>Executive product readout</p>
              </div>
            </div>
            <div className={styles.insightRows}>
              {INSIGHTS.map(([label, value], index) => (
                <div key={label} className={styles.insightRow} style={{ animationDelay: `${index * 70}ms` }}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => router.push(`/idea-discovery${idea ? `?idea=${encodeURIComponent(idea)}` : ''}`)}>
            <ArrowLeft size={18} />
            Edit Requirements
          </button>
          <button type="button" className={styles.primaryButton} onClick={continueToArchitecture}>
            Continue to Architecture
            <ChevronRight size={18} />
          </button>
          <button type="button" className={styles.secondaryButton}>
            <Download size={18} />
            Download Blueprint PDF
          </button>
        </footer>
      </section>
    </main>
  );
}

export default function ProductBlueprintPage() {
  return (
    <Suspense fallback={null}>
      <ProductBlueprintPageContent />
    </Suspense>
  );
}
