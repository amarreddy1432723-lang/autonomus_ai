'use client';

import { useEffect, useMemo, useState } from 'react';
import styles from './MissionControlProduct.module.css';
import { ChangeSummary } from './ChangeSummary';
import { DiffViewer } from './DiffViewer';
import { EvidenceExplorer } from './EvidenceExplorer';
import { MissionCompletion } from './MissionCompletion';
import { MissionControls } from './MissionControls';
import { MissionHeader } from './MissionHeader';
import { MissionMetrics } from './MissionMetrics';
import { MissionNotifications, type MissionNotification } from './MissionNotifications';
import { MissionProgress } from './MissionProgress';
import { MissionReport } from './MissionReport';
import { MissionTimeline } from './MissionTimeline';
import { RecoveryCenter } from './RecoveryCenter';
import { RepositoryLocks } from './RepositoryLocks';
import { TaskDag } from './TaskDag';
import { TaskInspector } from './TaskInspector';
import { VerificationPanel } from './VerificationPanel';
import { WorkforcePanel } from './WorkforcePanel';
import type {
  MissionControlChangeSet,
  MissionControlEdge,
  MissionControlEvent,
  MissionControlEvidence,
  MissionControlLock,
  MissionControlMetricsData,
  MissionControlMission,
  MissionControlRecovery,
  MissionControlTask,
  MissionControlVerificationStep,
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
  changeSet?: MissionControlChangeSet;
  verification?: MissionControlVerificationStep[];
  notifications?: MissionNotification[];
  onRefresh: () => void;
  onOpenWorkspace: () => void;
  onApproveAll?: () => void;
  onRejectAll?: () => void;
  onRollback?: () => void;
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
  changeSet,
  verification = [],
  notifications = [],
  onRefresh,
  onOpenWorkspace,
  onApproveAll,
  onRejectAll,
  onRollback,
}: MissionControlProductViewProps) {
  const [selectedTaskKey, setSelectedTaskKey] = useState(tasks[0]?.taskKey || '');
  const [timelineFilter, setTimelineFilter] = useState('All');
  const [selectedEvidenceId, setSelectedEvidenceId] = useState(evidence[0]?.id || '');
  const [selectedChangePath, setSelectedChangePath] = useState(changeSet?.files[0]?.path || '');
  const selectedTask = useMemo(
    () => tasks.find((task) => task.taskKey === selectedTaskKey) || tasks[0],
    [selectedTaskKey, tasks],
  );
  const visibleChangeSet: MissionControlChangeSet = changeSet || {
    title: 'Mission change set',
    summary: 'No repository change set has been recorded yet.',
    reviewState: 'not_created',
    files: [],
    rollbackAvailable: false,
  };

  useEffect(() => {
    if (visibleChangeSet.files.length === 0) {
      if (selectedChangePath) setSelectedChangePath('');
      return;
    }
    if (!visibleChangeSet.files.some((file) => file.path === selectedChangePath)) {
      setSelectedChangePath(visibleChangeSet.files[0].path);
    }
  }, [selectedChangePath, visibleChangeSet.files]);

  return (
    <div className={styles.shell}>
      <MissionNotifications items={notifications} />
      <MissionHeader mission={mission} onRefresh={onRefresh} onOpenWorkspace={onOpenWorkspace} />
      <div className={styles.topGrid}>
        <WorkforcePanel workers={workers} />
        <TaskDag tasks={tasks} edges={edges} selectedTaskKey={selectedTask?.taskKey} onSelectTask={(task) => setSelectedTaskKey(task.taskKey)} />
        <TaskInspector task={selectedTask} workers={workers} />
      </div>
      <div className={styles.bottomGrid}>
        <MissionTimeline events={events} filter={timelineFilter} onFilterChange={setTimelineFilter} />
        <div className={styles.workerList}>
          <MissionProgress metrics={metrics} />
          <MissionMetrics metrics={metrics} />
        </div>
      </div>
      <div className={styles.evidenceGrid}>
        <RepositoryLocks locks={locks} />
        <EvidenceExplorer evidence={evidence} selectedEvidenceId={selectedEvidenceId} onSelectEvidence={(item) => setSelectedEvidenceId(item.id)} />
      </div>
      <div className={styles.reviewGrid}>
        <ChangeSummary
          changeSet={visibleChangeSet}
          selectedPath={selectedChangePath}
          onSelectFile={(file) => setSelectedChangePath(file.path)}
          onApproveAll={onApproveAll}
          onRejectAll={onRejectAll}
          onRollback={onRollback}
        />
        <DiffViewer
          changeSet={visibleChangeSet}
          selectedPath={selectedChangePath}
          onSelectFile={(file) => setSelectedChangePath(file.path)}
          verification={verification}
        />
        <VerificationPanel checks={verification} />
      </div>
      <RecoveryCenter recovery={recovery} />
      <MissionControls
        manualReviewRequired={metrics.manualReviewRequired}
        onRefresh={onRefresh}
        onOpenWorkspace={onOpenWorkspace}
      />
      <MissionReport
        mission={mission}
        workers={workers}
        tasks={tasks}
        locks={locks}
        metrics={metrics}
        evidence={evidence}
        recovery={recovery}
        changeSet={visibleChangeSet}
        verification={verification}
      />
      <MissionCompletion mission={mission} metrics={metrics} />
    </div>
  );
}
