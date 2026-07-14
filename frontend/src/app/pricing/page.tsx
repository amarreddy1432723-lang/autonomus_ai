import Link from 'next/link';
import { ArrowRight, Check } from 'lucide-react';
import PublicNav from '../PublicNav';
import styles from '../publicSite.module.css';

const plans = [
  {
    name: 'Free',
    price: '$0',
    copy: 'Try Arceus with limited runs and local project exploration.',
    features: ['Basic Code workspace', 'Limited agent runs', 'Local folder open', 'Community docs'],
  },
  {
    name: 'Pro',
    price: '$20',
    copy: 'For individual builders who need Code, PA, and Interview workflows.',
    features: ['Higher agent limits', 'PA reminders and daily brief', 'Interview answer generations', 'GitHub PR flow'],
  },
  {
    name: 'Team',
    price: '$40',
    copy: 'For shared engineering workspaces, org billing, and admin visibility.',
    features: ['Team seats', 'Shared Code projects', 'Audit logs', 'Admin monitoring'],
  },
];

export default function PricingPage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Pricing</div>
        <h1>Start locally. Upgrade when Arceus saves serious engineering time.</h1>
        <p>Plan limits are enforced by product area: Code jobs, sandbox minutes, PA automations, Interview sessions, storage, GitHub PRs, and model usage.</p>
      </section>
      <section className={styles.section}>
        <div className={styles.grid}>
          {plans.map((plan) => (
            <div className={styles.card} key={plan.name}>
              <span className={styles.pill}>{plan.name}</span>
              <h2>{plan.name}</h2>
              <div className={styles.price}>{plan.price}<span className={styles.muted}> / month</span></div>
              <p>{plan.copy}</p>
              <ul>
                {plan.features.map((feature) => (
                  <li key={feature}><Check size={13} /> {feature}</li>
                ))}
              </ul>
              <div className={styles.actions}>
                <Link className={styles.primary} href="/signup">Choose {plan.name} <ArrowRight size={14} /></Link>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
