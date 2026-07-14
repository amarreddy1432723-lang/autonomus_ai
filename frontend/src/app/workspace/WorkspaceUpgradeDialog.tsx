import styles from './Workspace.module.css';

type WorkspaceUpgradeDialogProps = {
  upgradePrompt: any;
  onClose: () => void;
};

export default function WorkspaceUpgradeDialog({ upgradePrompt, onClose }: WorkspaceUpgradeDialogProps) {
  if (!upgradePrompt) return null;

  return (
    <div className={styles.replaceDialogBackdrop} role="presentation" onMouseDown={onClose}>
      <div className={styles.upgradeDialog} role="dialog" aria-label="Upgrade required" onMouseDown={(event) => event.stopPropagation()}>
        <span className={styles.upgradeEyebrow}>{upgradePrompt.code || 'LIMIT_REACHED'}</span>
        <strong>{upgradePrompt.upgrade_prompt || upgradePrompt.message || 'Upgrade required to continue.'}</strong>
        <p>{upgradePrompt.message || 'This action is protected by your current Arceus plan limits.'}</p>
        <div className={styles.upgradeUsageGrid}>
          <div><span>Plan</span><em>{upgradePrompt.plan || 'free'}</em></div>
          <div><span>Action</span><em>{upgradePrompt.action || upgradePrompt.feature || 'workspace action'}</em></div>
          <div><span>Used</span><em>{upgradePrompt.used ?? '-'}</em></div>
          <div><span>Limit</span><em>{upgradePrompt.limit ?? 'locked'}</em></div>
        </div>
        <div className={styles.upgradeActions}>
          <button type="button" onClick={onClose}>Not now</button>
          <button type="button" onClick={() => { window.location.href = upgradePrompt.upgrade_url || '/settings?tab=billing'; }}>Upgrade Now</button>
        </div>
      </div>
    </div>
  );
}
