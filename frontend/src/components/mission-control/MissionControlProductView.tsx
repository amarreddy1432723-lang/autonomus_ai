import styles from './MissionControlProduct.module.css';
import { EvidenceExplorer } from './EvidenceExplorer';
import { MissionCompletion } from './MissionCompletion';
import { MissionControls } from './MissionControls';
import { MissionHeader } from './MissionHeader';
import { MissionMetrics } from './MissionMetrics';
import { MissionProgress } from './MissionProgress';
import { MissionTimeline } from './MissionTimeline';
import { RecoveryCenter } from './RecoveryCenter';
import { RepositoryLocks } from './RepositoryLocks';
import { TaskDag } from './TaskDag';
import { WorkforcePanel } from './WorkforcePanel';
import type {
  MissionControlEdge,
  MissionControlEvent,
  MissionControlEvidence,
  MissionControlLock,
  MissionControlMetricsData,
  MissionControlMission,
  MissionControlRecovery,
  MissionControlTask,
  MissionControlWorker,
} from './types';

type MissionControlProductViewProps = {
  mission: MissionControlMission;
  workers: MissionControlWorker[];
  tasks: MissionControlTask[];
  edges: MissionControlEdge[];
  events: MissionControlEvent[];
  locks: MissionControlLock[];
  metrics: MissionControlMetricsData;
  evidence: MissionControlEvidence[];
  recovery: MissionControlRecovery[];
  onRefresh: () => void;
  onOpenWorkspace: () => void;
};

export function MissionControlProductView({
  mission,
  workers,
  tasks,
  edges,
  events,
  locks,
  metrics,
  evidence,
  recovery,
  onRefresh,
  onOpenWorkspace,
}: MissionControlProductViewProps) {
  return (
    <div className={styles.shell}>
      <MissionHeader mission={mission} onRefresh={onRefresh} onOpenWorkspace={onOpenWorkspace} />
      <div className={styles.topGrid}>
        <WorkforcePanel workers={workers} />
        <TaskDag tasks={tasks} edges={edges} />
      </div>
      <div className={styles.bottomGrid}>
        <MissionTimeline events={events} />
        <div className={styles.workerList}>
          <MissionProgress metrics={metrics} />
          <MissionMetrics metrics={metrics} />
        </div>
      </div>
      <div className={styles.topGrid}>
        <RepositoryLocks locks={locks} />
        <EvidenceExplorer evidence={evidence} />
      </div>
      <RecoveryCenter recovery={recovery} />
      <MissionControls
        manualReviewRequired={metrics.manualReviewRequired}
        onRefresh={onRefresh}
        onOpenWorkspace={onOpenWorkspace}
      />
      <MissionCompletion mission={mission} metrics={metrics} />
    </div>
  );
}
