import styles from './MissionControlProduct.module.css';
import { formatDuration } from './statusCopy';
import type { MissionControlMetricsData } from './types';

type Metric = {
  label: string;
  value: string;
  detail: string;
};

export function MissionMetrics({ metrics }: { metrics: MissionControlMetricsData }) {
  const items: Metric[] = [
    { label: 'Tasks', value: `${metrics.completedTasks || 0}/${metrics.taskCount || 0}`, detail: 'Completed mission work' },
    { label: 'Workers', value: String(metrics.activeAssignments || 0), detail: 'Currently assigned' },
    { label: 'Ready', value: String(metrics.readyTasks || 0), detail: 'Can run next' },
    { label: 'Blocked', value: String(metrics.blockedTasks || 0), detail: 'Need attention' },
    { label: 'Evidence', value: String(metrics.evidenceCount || 0), detail: 'Proof records collected' },
    { label: 'Runtime', value: formatDuration(metrics.missionDurationSeconds), detail: 'Mission duration' },
  ];

  return (
    <section className={styles.panel} aria-label="Mission metrics">
      <header>
        <div>
          <h3>Mission Metrics</h3>
          <p>Small, trustworthy numbers for execution health.</p>
        </div>
      </header>
      <div className={styles.metricGrid}>
        {items.map((item) => (
          <article key={item.label} className={styles.metric}>
            <b>{item.value}</b>
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
