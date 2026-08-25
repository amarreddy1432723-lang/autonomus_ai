import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { ArrowRight, Building2, LockKeyhole, ShieldCheck } from 'lucide-react';
import PublicNav from '../PublicNav';
import styles from '../publicSite.module.css';

const enterpriseItems: Array<[string, string, LucideIcon]> = [
  ['Security governance', 'SSO, audit trails, policy gates, and role-aware approvals for engineering missions.', ShieldCheck],
  ['Private deployment', 'Run Arceus with dedicated infrastructure, controlled networking, and release governance.', Building2],
  ['Credential control', 'Scope secrets, service accounts, model providers, and repository access through policy.', LockKeyhole],
];

export default function EnterprisePage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={`${styles.section} ${styles.hero}`}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Enterprise</span>
          <h1>AI engineering operations for governed teams.</h1>
          <p>
            Arceus Enterprise is designed for organizations that need private repositories, strict approvals,
            auditable AI work, controlled model routing, and release safety.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primary} href="/sign-in">
              Talk to Arceus <ArrowRight size={17} />
            </Link>
            <Link className={styles.secondary} href="/docs">Read docs</Link>
          </div>
        </div>
      </section>
      <section className={styles.section}>
        <div className={styles.cardGrid}>
          {enterpriseItems.map(([title, body, Icon]) => (
            <article className={styles.card} key={title}>
              <Icon size={22} />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
