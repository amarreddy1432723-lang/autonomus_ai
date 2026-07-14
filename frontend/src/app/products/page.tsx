import Link from 'next/link';
import { ArrowRight, BriefcaseBusiness, Code2, Mic } from 'lucide-react';
import PublicNav from '../PublicNav';
import styles from '../publicSite.module.css';

const products = [
  {
    name: 'Arceus Code',
    href: '/products/code',
    icon: Code2,
    status: 'Desktop-first',
    copy: 'AI software engineering workspace for local folders, terminal, patch review, project analysis, and next-action guidance.',
    actions: ['Open repositories', 'Run commands', 'Review diffs', 'Create PRs'],
  },
  {
    name: 'Arceus PA',
    href: '/products/pa',
    icon: BriefcaseBusiness,
    status: 'Mobile + desktop',
    copy: 'Personal assistant OS for daily briefs, tasks, reminders, memory, approvals, and automation safety.',
    actions: ['Plan the day', 'Create reminders', 'Track approvals', 'Pause automations'],
  },
  {
    name: 'Arceus Interview',
    href: '/products/interview',
    icon: Mic,
    status: 'Desktop cockpit',
    copy: 'Resume-aware interview assistant with live transcript support, company prep, and concise answer coaching.',
    actions: ['Upload resume', 'Practice answers', 'Live coaching', 'Save interview memory'],
  },
];

export default function ProductsPage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Products</div>
        <h1>Choose the Arceus product for the job.</h1>
        <p>Each product has a separate workflow, memory scope, settings surface, and entitlement path under one Arceus account.</p>
      </section>
      <section className={styles.section}>
        <div className={styles.grid}>
          {products.map((product) => {
            const Icon = product.icon;
            return (
              <Link className={styles.card} href={product.href} key={product.name}>
                <span className={styles.pill}><Icon size={13} /> {product.status}</span>
                <h2>{product.name}</h2>
                <p>{product.copy}</p>
                <ul>
                  {product.actions.map((action) => <li key={action}>{action}</li>)}
                </ul>
                <p><strong>Explore</strong> <ArrowRight size={13} /></p>
              </Link>
            );
          })}
        </div>
      </section>
    </main>
  );
}
