import styles from './MissionControlProduct.module.css';
import type { MissionControlEvidence } from './types';

export function EvidenceExplorer({ evidence }: { evidence: MissionControlEvidence[] }) {
  const visibleEvidence = evidence.slice(0, 6);

  return (
    <section className={styles.panel} aria-label="Evidence explorer">
      <header>
        <div>
          <h3>Evidence</h3>
          <p>Build, test, tool, and review proof attached to the mission.</p>
        </div>
        <span className={styles.taskBadge}>{evidence.length} records</span>
      </header>
      <div className={styles.evidenceList}>
        {visibleEvidence.length === 0 && <div className={styles.empty}>No evidence has been collected yet.</div>}
        {visibleEvidence.map((item) => (
          <article key={item.id} className={styles.evidenceItem}>
            <strong>{item.summary}</strong>
            <small>{item.evidenceType || 'evidence'} · {item.status}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
