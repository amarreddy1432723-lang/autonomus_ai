import { Clock3, ShieldCheck } from 'lucide-react';
import styles from './MissionControlProduct.module.css';
import { taskStatusLabel } from './statusCopy';
import type { MissionControlTask, MissionControlWorker } from './types';

export function TaskInspector({
  task,
  workers,
}: {
  task?: MissionControlTask;
  workers: MissionControlWorker[];
}) {
  const owner = task
    ? workers.find((worker) => worker.currentTaskKey === task.taskKey || worker.currentTaskTitle === task.title)
    : undefined;
  const criteria = task?.acceptanceCriteria?.length
    ? task.acceptanceCriteria
    : ['Linked to mission objective', 'Evidence required before completion', 'Independent review required when risk is material'];

  return (
    <section className={styles.panel} aria-label="Selected task details">
      <header>
        <div>
          <h3>Task Details</h3>
          <p>{task ? 'Selected execution node and its proof requirements.' : 'Select a task in the execution graph.'}</p>
        </div>
        {task && <span className={styles.taskBadge}>{taskStatusLabel(task.status)}</span>}
      </header>
      {!task ? (
        <div className={styles.empty}>No task selected yet.</div>
      ) : (
        <div className={styles.inspector}>
          <strong>{task.title || task.taskKey}</strong>
          <p>{task.blockedReason || 'Dependencies are clear. The scheduler can move this task when policy allows it.'}</p>
          <div className={styles.detailGrid}>
            <span><b>Owner</b>{owner?.role || task.ownerRole || 'Scheduler'}</span>
            <span><b>Assignment</b>{task.assignmentStatus || 'waiting'}</span>
            <span><b>Evidence</b>{task.evidenceCount ?? 0} record(s)</span>
            <span><b>Updated</b>{task.updatedAt ? new Date(task.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'live'}</span>
          </div>
          <div className={styles.criteriaList}>
            {criteria.map((item) => (
              <span key={item}><ShieldCheck size={13} /> {item}</span>
            ))}
          </div>
          <small><Clock3 size={13} /> Failed checks or conflicts block dependent tasks automatically.</small>
        </div>
      )}
    </section>
  );
}
