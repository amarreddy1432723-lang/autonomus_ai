import styles from './MissionControlProduct.module.css';
import type { MissionControlEvidence } from './types';

export function EvidenceExplorer({
  evidence,
  selectedEvidenceId,
  onSelectEvidence,
}: {
  evidence: MissionControlEvidence[];
  selectedEvidenceId?: string;
  onSelectEvidence?: (evidence: MissionControlEvidence) => void;
}) {
  const visibleEvidence = evidence.slice(0, 6);
  const selected = evidence.find((item) => item.id === selectedEvidenceId) || visibleEvidence[0];

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
          <button
            type="button"
            key={item.id}
            className={styles.evidenceItem}
            data-selected={selected?.id === item.id}
            onClick={() => onSelectEvidence?.(item)}
          >
            <strong>{item.summary}</strong>
            <small>{item.evidenceType || 'evidence'} · {item.status} · {item.trustLevel || 'unverified'}</small>
          </button>
        ))}
      </div>
      {selected && (
        <article className={styles.evidenceDetail}>
          <strong>{selected.tool || selected.evidenceType || 'Evidence record'}</strong>
          <p>{selected.outputSummary || selected.inputSummary || selected.summary}</p>
          <small>{selected.durationMs != null ? `${selected.durationMs} ms` : 'duration not recorded'} · {selected.createdAt || 'live'}</small>
        </article>
      )}
    </section>
  );
}
