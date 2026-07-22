import styles from './AppShell.module.css';

type WorkspaceStatusBarProps = {
  branch?: string;
  diagnostics?: number;
  serviceState?: string;
  modelState?: string;
};

export default function WorkspaceStatusBar({
  branch = 'main',
  diagnostics = 0,
  serviceState = 'Ready',
  modelState = 'Models healthy',
}: WorkspaceStatusBarProps) {
  return (
    <div className={styles.statusBar}>
      <span className={styles.statusCluster}>
        <span>{branch}</span>
        <span>{diagnostics} problems</span>
      </span>
      <span className={styles.statusCluster}>
        <span>{serviceState}</span>
        <span>{modelState}</span>
      </span>
    </div>
  );
}
