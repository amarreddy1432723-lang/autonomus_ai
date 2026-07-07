'use client';

import Link from 'next/link';
import { BrainCircuit, BriefcaseBusiness, Cpu, Globe2, Mic, Palette, Rocket, Settings } from 'lucide-react';
import AppShell from '../../components/AppShell';
import styles from '../nexus.module.css';

const products = [
  { name: 'NEXUS Code', href: '/studio', icon: Cpu, detail: 'AI coding engine, planning, patches, deploy handoff' },
  { name: 'NEXUS PA', href: '/pa', icon: BriefcaseBusiness, detail: 'Personal assistant for briefs, schedules, delegation' },
  { name: 'Interview', href: '/interview', icon: Mic, detail: 'Resume-aware live coaching and practice' },
  { name: 'Design', href: '/design', icon: Palette, detail: 'UI/UX variants and implementation handoff' },
  { name: 'Deploy', href: '/deploy', icon: Rocket, detail: 'Analyze and prepare production deployments' },
  { name: 'Research', href: '/internet', icon: Globe2, detail: 'Deep web research and free-tier discovery' },
];

export default function HubPage() {
  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.hubHero}>
          <div className={styles.eyebrow}>NEXUS AI Platform</div>
          <h1 className={styles.title}>Your AI-powered product suite</h1>
          <p className={styles.subtitle}>One shared intelligence layer across coding, personal assistance, interviews, design, deployment, and research.</p>
        </section>
        <section className={styles.productGrid}>
          {products.map((product) => {
            const Icon = product.icon;
            return (
              <Link className={styles.productCard} href={product.href} key={product.name}>
                <Icon size={30} />
                <h2>{product.name}</h2>
                <p>{product.detail}</p>
              </Link>
            );
          })}
        </section>
        <section className={styles.actionBar}>
          <Link className={styles.secondaryButton} href="/life-graph"><BrainCircuit size={16} /> Life Graph</Link>
          <Link className={styles.secondaryButton} href="/settings"><Settings size={16} /> Settings</Link>
        </section>
      </main>
    </AppShell>
  );
}
