import Link from 'next/link';
import { ArrowRight, Brain, Code2, Mic, ShieldCheck, Sparkles } from 'lucide-react';
import PublicNav from './PublicNav';
import styles from './publicSite.module.css';

const products = [
  {
    name: 'Arceus Code',
    href: '/products/code',
    icon: Code2,
    copy: 'Desktop AI engineering workspace for opening real projects, analyzing structure, planning next work, editing code, running commands, and reviewing patches.',
  },
  {
    name: 'Arceus PA',
    href: '/products/pa',
    icon: Sparkles,
    copy: 'Personal AI operating layer for daily planning, reminders, briefings, memory, approvals, and mobile-first assistance.',
  },
  {
    name: 'Arceus Interview',
    href: '/products/interview',
    icon: Mic,
    copy: 'Desktop interview cockpit for resume-aware answers, live transcript support, role prep, and concise answer coaching.',
  },
];

export default function Home() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Arceus AI Platform</div>
        <h1>Build, plan, and operate your work with AI that knows the next step.</h1>
        <p>
          Arceus separates the public Hub, account and billing management, and downloadable desktop products.
          Arceus Code is the engineering workspace; PA and Interview stay focused on their own jobs.
        </p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/products/code">
            Explore Arceus Code <ArrowRight size={15} />
          </Link>
          <Link className={styles.secondary} href="/download">Download desktop app</Link>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <div className={styles.eyebrow}>Products</div>
            <h2>One Arceus account, separate product surfaces.</h2>
          </div>
          <Link className={styles.secondary} href="/products">View all products</Link>
        </div>
        <div className={styles.grid}>
          {products.map((product) => {
            const Icon = product.icon;
            return (
              <Link className={styles.card} href={product.href} key={product.name}>
                <span className={styles.pill}><Icon size={13} /> Product</span>
                <h2>{product.name}</h2>
                <p>{product.copy}</p>
              </Link>
            );
          })}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <div className={styles.eyebrow}>Flow</div>
            <h2>Website sells and manages. Desktop does the engineering work.</h2>
          </div>
        </div>
        <div className={styles.flow}>
          {['Choose product', 'Download app', 'Sign in securely', 'Open project', 'Analyze codebase', 'Approve next action'].map((step, index) => (
            <div className={styles.flowStep} key={step}>
              <span className={styles.pill}>0{index + 1}</span>
              <strong>{step}</strong>
              <span className={styles.muted}>A clear stage in the Arceus user journey.</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.grid}>
          <div className={styles.card}>
            <ShieldCheck size={22} />
            <h3>Production safety</h3>
            <p>Admin readiness, billing health, smoke tests, rate limits, backups, release gates, and audit logs are part of the platform surface.</p>
          </div>
          <div className={styles.card}>
            <Brain size={22} />
            <h3>Project brain</h3>
            <p>Arceus Code should not only answer prompts. It should explain what to do next, why it matters, how to do it manually, and what it can safely automate.</p>
          </div>
        </div>
      </section>
      <footer className={styles.footer}>Arceus is under active development. Production downloads require signed release artifacts.</footer>
    </main>
  );
}
