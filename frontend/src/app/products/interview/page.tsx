import Link from 'next/link';
import { ArrowRight, Building2, FileText, Mic, MessageSquareText } from 'lucide-react';
import PublicNav from '../../PublicNav';
import styles from '../../publicSite.module.css';

export default function ArceusInterviewProductPage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Arceus Interview</div>
        <h1>Interview prep and live answer support grounded in your resume.</h1>
        <p>Arceus Interview is a desktop interview cockpit for resume upload, company and role prep, question capture, concise answers, and structured interview memory.</p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/interview">Open Interview <ArrowRight size={15} /></Link>
          <Link className={styles.secondary} href="/pricing">View plans</Link>
        </div>
      </section>
      <section className={styles.section}>
        <div className={styles.grid}>
          {[
            [FileText, 'Resume-aware answers', 'Use candidate profile context without forcing resume details into technical answers.'],
            [Mic, 'Live cockpit', 'Desktop transcript and answer workflow for Chrome or Edge microphone capture.'],
            [Building2, 'Company and role prep', 'Cache company and role context so answers stay relevant under pressure.'],
            [MessageSquareText, 'Answer coaching', 'Improve phrasing, identify missing points, and prepare likely follow-up answers.'],
          ].map(([Icon, title, copy]) => {
            const TypedIcon = Icon as typeof FileText;
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
