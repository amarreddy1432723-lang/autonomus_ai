import { RefreshCw, Rocket } from 'lucide-react';
import styles from './MissionControlProduct.module.css';
import { formatDuration, missionStatusLabel } from './statusCopy';
import type { MissionControlMission } from './types';

type MissionHeaderProps = {
  mission: MissionControlMission;
  onRefresh: () => void;
  onOpenWorkspace: () => void;
};

function progressPercent(progress?: number) {
  const value = typeof progress === 'number' && Number.isFinite(progress) ? progress : 0;
  return Math.max(0, Math.min(100, value <= 1 ? Math.round(value * 100) : Math.round(value)));
}

export function MissionHeader({ mission, onRefresh, onOpenWorkspace }: MissionHeaderProps) {
  const progress = progressPercent(mission.progress);

  return (
    <section className={styles.missionHeader} aria-label="Mission summary">
      <div>
        <span className={styles.statusPill} data-state={mission.status}>
          {missionStatusLabel(mission.status)}
        </span>
        <h2>{mission.title || 'Engineering Mission Control'}</h2>
        <p>
          {mission.repositoryName || 'Active repository'} · Running for {formatDuration(mission.durationSeconds)}
        </p>
        <div className={styles.progressRow} aria-label={`Mission progress ${progress}%`}>
          <i><em style={{ width: `${progress}%` }} /></i>
          <strong>{progress}%</strong>
        </div>
      </div>
      <div className={styles.controls}>
        <button type="button" onClick={onRefresh}>
          <RefreshCw size={14} /> Refresh
        </button>
        <button type="button" data-primary="true" onClick={onOpenWorkspace}>
          <Rocket size={14} /> Open workspace
        </button>
      </div>
    </section>
  );
}
