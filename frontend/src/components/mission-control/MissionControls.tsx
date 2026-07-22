import { Pause, RefreshCw, ShieldCheck } from 'lucide-react';
import styles from './MissionControlProduct.module.css';

type MissionControlsProps = {
  manualReviewRequired?: number;
  onRefresh: () => void;
  onOpenWorkspace: () => void;
};

export function MissionControls({ manualReviewRequired = 0, onRefresh, onOpenWorkspace }: MissionControlsProps) {
  return (
    <section className={styles.completion} aria-label="Mission controls">
      <div>
        <h3>{manualReviewRequired > 0 ? 'Review needed before continuing' : 'Execution is under control'}</h3>
        <p>
          {manualReviewRequired > 0
            ? `${manualReviewRequired} item(s) need human review before PR or deploy.`
            : 'Arceus is collecting evidence and keeping the mission recoverable.'}
        </p>
      </div>
      <div className={styles.completionActions}>
        <button type="button" onClick={onRefresh}><RefreshCw size={14} /> Retry runtime</button>
        <button type="button"><Pause size={14} /> Pause</button>
        <button type="button" data-primary="true" onClick={onOpenWorkspace}><ShieldCheck size={14} /> Review work</button>
      </div>
    </section>
  );
}
