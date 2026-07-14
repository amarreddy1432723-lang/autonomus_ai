import Link from 'next/link';
import { ArrowRight, Bell, Brain, CalendarClock, PauseCircle } from 'lucide-react';
import PublicNav from '../../PublicNav';
import styles from '../../publicSite.module.css';

export default function ArceusPAProductPage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Arceus PA</div>
        <h1>Your personal AI operating layer for daily life and work.</h1>
        <p>Arceus PA is separate from Code and Interview. It focuses on mobile-first assistance, reminders, daily briefs, memory, approvals, and safe automation.</p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/pa">Open PA preview <ArrowRight size={15} /></Link>
          <Link className={styles.secondary} href="/pricing">View plans</Link>
        </div>
      </section>
      <section className={styles.section}>
        <div className={styles.grid}>
          {[
            [CalendarClock, 'Daily brief', 'Generate a focused plan from tasks, schedules, reminders, memories, and approvals.'],
            [Bell, 'Reminders and notifications', 'Create, update, and track reminders with in-app notifications first.'],
            [PauseCircle, 'Emergency pause', 'Stop background automations immediately without affecting Code or Interview.'],
            [Brain, 'Personal memory', 'Keep PA-scoped preferences and context separate from engineering and interview data.'],
          ].map(([Icon, title, copy]) => {
            const TypedIcon = Icon as typeof CalendarClock;
            return (
              <div className={styles.card} key={String(title)}>
                <TypedIcon size={22} />
                <h2>{title as string}</h2>
                <p>{copy as string}</p>
              </div>
            );
          })}
        </div>
      </section>
    </main>
  );
}
