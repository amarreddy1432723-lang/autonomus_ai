'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Bell,
  Check,
  ChevronRight,
  FileText,
  Lightbulb,
  Rocket,
  Search,
  Sparkles,
  UserRound,
} from 'lucide-react';
import styles from './EvolutionCenter.module.css';

const HEALTH = [
  ['Availability', '99.98%', 'Excellent'],
  ['Performance', 'Excellent', 'Fast response'],
  ['Security', 'Excellent', 'Protected'],
  ['Accessibility', '95%', 'Strong'],
  ['Customer Satisfaction', '4.8/5', 'Growing'],
  ['Crash Rate', '0.02%', 'Stable'],
  ['Deployment Health', 'Healthy', 'Live'],
];

const RECOMMENDATIONS = [
  ['Introduce Offline Mode', 'High', '★★★★★', 'Medium', 'Protects users when connectivity drops.'],
  ['Implement Passkeys', 'High', '★★★★☆', 'Low', 'Improves security and reduces login friction.'],
  ['Add Team Collaboration', 'Requested by 68% of users', '★★★★★', 'High', 'Unlocks team and enterprise adoption.'],
  ['Optimize Image Loading', '18% performance gain', '★★★★☆', 'Low', 'Improves page speed and conversion.'],
  ['Support Multiple Languages', 'Growth opportunity high', '★★★★☆', 'Medium', 'Expands reachable markets.'],
];

const RELEASES = [
  ['Release 1.2', 'Ready', ['Dark Mode', 'Notifications', 'Bug Fixes']],
  ['Release 1.3', 'Planning', ['AI Planning', 'Workflow Templates', 'Memory Improvements']],
  ['Release 2.0', 'Research', ['Marketplace', 'Extensions', 'Plugin SDK']],
];

const ENGINEERS = [
  ['Engineering Manager', 'Planning Sprint 5', '98%', 'Today'],
  ['Architect', 'Reviewing improvements', '96%', '2h'],
  ['Frontend', 'Building Dark Mode', '94%', '1d'],
  ['Backend', 'Performance optimization', '93%', '18h'],
  ['QA', 'Regression testing', '95%', '6h'],
  ['Security', 'Compliance review', '97%', 'Tomorrow'],
  ['DevOps', 'Preparing next deployment', '92%', '4h'],
  ['Documentation', 'Updating guides', '99%', 'Today'],
];

const BUSINESS = [
  ['Monthly Active Users', '12.8k', 'up 18%'],
  ['Revenue Trend', '+24%', 'monthly'],
  ['Customer Growth', 'Strong', 'healthy'],
  ['Infrastructure Cost', '$184', 'stable'],
  ['AI Cost', '$62', 'within plan'],
  ['Budget Health', 'Excellent', 'safe'],
];

const VISION = ['Now', 'Next Release', 'Quarter Goals', 'Annual Vision', 'Long-Term Roadmap'];

function EvolutionCenterPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const stack = searchParams.get('stack') || 'recommended';

  const openWorkspace = () => {
    const params = new URLSearchParams();
    params.set('stage', 'evolution');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/workspace?${params.toString()}`);
  };

  const openKnowledgeGraph = () => {
    const params = new URLSearchParams();
    params.set('stage', 'knowledge');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/knowledge-graph?${params.toString()}`);
  };

  return (
    <main className={styles.evolution}>
      <section className={styles.window} aria-label="Arceus Code evolution center">
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <span>A</span>
            <div>
              <strong>Arceus Code</strong>
              <small>Healthcare AI Platform · Production · v1.0.0</small>
            </div>
          </div>
          <label className={styles.search}>
            <Search size={17} />
            <input aria-label="Search product intelligence" placeholder="Search product, releases, insights..." />
          </label>
          <div className={styles.actions}>
            <button type="button" aria-label="Notifications"><Bell size={18} /></button>
            <button type="button" aria-label="Profile"><UserRound size={18} /></button>
          </div>
        </header>

        <section className={styles.hero}>
          <p><span /> Production Healthy</p>
          <h1>Evolution Center</h1>
          <strong>Your product is live. Your AI engineering organization is continuously helping it evolve.</strong>
        </section>

        <section className={styles.mainGrid}>
          <section className={styles.health}>
            <header><h2>Product Health</h2><small>Production confidence at a glance.</small></header>
            <div className={styles.healthGrid}>
              {HEALTH.map(([label, value, detail]) => (
                <article key={label} className={styles.healthCard}>
                  <span><Check size={15} /></span>
                  <small>{label}</small>
                  <strong>{value}</strong>
                  <em>{detail}</em>
                </article>
              ))}
            </div>
          </section>

          <aside className={styles.business}>
            <header><h2>Business Intelligence</h2><small>Strategy signals without analytics noise.</small></header>
            <div>
              {BUSINESS.map(([label, value, detail]) => (
                <article key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>{detail}</small>
                </article>
              ))}
            </div>
          </aside>
        </section>

        <section className={styles.middleGrid}>
          <article className={styles.recommendations}>
            <header><h2>AI CTO Recommendations</h2><small>Strategic improvements proposed by Arceus.</small></header>
            <div className={styles.recommendationList}>
              {RECOMMENDATIONS.map(([title, impact, value, effort, note], index) => (
                <section key={title} className={styles.recommendationCard} style={{ animationDelay: `${index * 80}ms` }}>
                  <div>
                    <span><Lightbulb size={17} /></span>
                    <h3>{title}</h3>
                    <p>{note}</p>
                  </div>
                  <footer>
                    <b>Impact <em>{impact}</em></b>
                    <b>Business Value <em>{value}</em></b>
                    <b>Effort <em>{effort}</em></b>
                  </footer>
                </section>
              ))}
            </div>
          </article>

          <article className={styles.releases}>
            <header><h2>Upcoming Releases</h2><small>Planned product evolution.</small></header>
            <div className={styles.releaseList}>
              {RELEASES.map(([release, state, items]) => (
                <section key={release as string} className={styles.releaseCard}>
                  <div>
                    <h3>{release}</h3>
                    <span>{state}</span>
                  </div>
                  {(items as string[]).map((item) => <p key={item}><Check size={14} />{item}</p>)}
                </section>
              ))}
            </div>
          </article>

          <article className={styles.organization}>
            <header><h2>AI Engineering Organization</h2><small>Your permanent AI CTO team.</small></header>
            <div>
              {ENGINEERS.map(([role, objective, confidence, eta]) => (
                <button type="button" key={role}>
                  <span>{role.slice(0, 2).toUpperCase()}</span>
                  <div>
                    <strong>{role}</strong>
                    <small>{objective}</small>
                  </div>
                  <b>{confidence}</b>
                  <em>{eta}</em>
                </button>
              ))}
            </div>
          </article>
        </section>

        <section className={styles.vision}>
          <header>
            <h2>Future Vision</h2>
            <small>Your software never stops improving because your AI organization never stops thinking.</small>
          </header>
          <div>
            {VISION.map((item, index) => (
              <article key={item}>
                <span>{index + 1}</span>
                <strong>{item}</strong>
                {index < VISION.length - 1 ? <ChevronRight size={18} /> : null}
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.footer}>
          <button type="button"><Rocket size={17} /> Plan Next Release</button>
          <button type="button" onClick={openKnowledgeGraph}><Sparkles size={17} /> Review Recommendations</button>
          <button type="button" onClick={openWorkspace}>Open Engineering Workspace</button>
          <button type="button"><FileText size={17} /> Generate Executive Report</button>
        </footer>
      </section>
    </main>
  );
}

export default function EvolutionCenterPage() {
  return (
    <Suspense fallback={null}>
      <EvolutionCenterPageContent />
    </Suspense>
  );
}
