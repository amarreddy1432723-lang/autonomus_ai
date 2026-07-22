import styles from './MissionControlProduct.module.css';
import type { MissionControlWorker } from './types';
import { WorkerCard } from './WorkerCard';

const FALLBACK_WORKERS: MissionControlWorker[] = [
  { role: 'Mission Lead', status: 'ready', currentTaskTitle: 'Coordinating the mission' },
  { role: 'Implementation Engineer', status: 'ready', currentTaskTitle: 'Waiting for approved task' },
  { role: 'QA Reviewer', status: 'ready', currentTaskTitle: 'Preparing verification evidence' },
];

export function WorkforcePanel({ workers }: { workers: MissionControlWorker[] }) {
  const visibleWorkers = workers.length > 0 ? workers : FALLBACK_WORKERS;

  return (
    <section className={styles.panel} aria-label="AI workforce">
      <header>
        <div>
          <h3>AI Workforce</h3>
          <p>Your engineering organization, mapped to real runtime workers.</p>
        </div>
        <span className={styles.taskBadge}>{visibleWorkers.length} active</span>
      </header>
      <div className={styles.workerList}>
        {visibleWorkers.map((worker, index) => (
          <WorkerCard key={worker.workerId || `${worker.role}-${index}`} worker={worker} />
        ))}
      </div>
    </section>
  );
}
