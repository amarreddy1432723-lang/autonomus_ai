import Link from 'next/link';
import { ArrowRight, BookOpen, Download, FolderOpen, ShieldCheck, Terminal } from 'lucide-react';
import PublicNav from '../PublicNav';
import styles from '../publicSite.module.css';

const docs = [
  ['Installation', 'Download and install Arceus Code for Windows, macOS, or Linux.', Download],
  ['First project', 'Open a folder, review permissions, run analysis, and inspect next actions.', FolderOpen],
  ['Terminal and commands', 'Run safe local commands from the selected trusted project folder.', Terminal],
  ['Privacy and security', 'Understand local folder access, approvals, auth, billing, and audit logs.', ShieldCheck],
];

export default function DocsPage() {
  return (
    <main className={styles.site}>
      <PublicNav />
      <section className={styles.hero}>
        <div className={styles.eyebrow}>Docs</div>
        <h1>Install Arceus, open your first project, and understand the safety model.</h1>
        <p>This public docs surface links the product story to the engineering runbooks already kept in the repository.</p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/download">Download Arceus Code <ArrowRight size={15} /></Link>
          <Link className={styles.secondary} href="/products/code">Read product overview</Link>
        </div>
      </section>
      <section className={styles.section}>
        <div className={styles.grid}>
          {docs.map(([title, copy, Icon]) => {
            const TypedIcon = Icon as typeof BookOpen;
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
