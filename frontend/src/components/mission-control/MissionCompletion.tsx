import styles from './MissionControlProduct.module.css';
import type { MissionControlMetricsData, MissionControlMission } from './types';

export function MissionCompletion({
  mission,
  metrics,
}: {
  mission: MissionControlMission;
  metrics: MissionControlMetricsData;
}) {
  const complete = mission.status === 'completed';
  const failed = mission.status === 'failed' || mission.status === 'attention_required';

  return (
    <section className={styles.completion} aria-label="Mission completion">
      <div>
        <h3>{complete ? 'Mission proof is complete' : failed ? 'Mission needs a decision' : 'Mission proof is building'}</h3>
        <p>
          {complete
            ? `${metrics.evidenceCount || 0} evidence record(s) are available for final review.`
            : failed
              ? 'Open recovery before approving more work.'
              : 'Completion requires tasks, evidence, verification, and human review when required.'}
        </p>
      </div>
      <span className={styles.statusPill} data-state={mission.status}>
        {complete ? 'Ready for PR' : failed ? 'Action required' : 'In progress'}
      </span>
    </section>
  );
}
