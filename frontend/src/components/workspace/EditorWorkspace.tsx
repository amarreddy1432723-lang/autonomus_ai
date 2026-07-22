import type { ReactNode } from 'react';
import styles from './AppShell.module.css';

type EditorWorkspaceProps = {
  children?: ReactNode;
};

export default function EditorWorkspace({ children }: EditorWorkspaceProps) {
  if (children) return <>{children}</>;

  return (
    <div className={styles.emptyEditor}>
      <div>
        <strong>Select a file to inspect</strong>
        <p>Open a workspace file, review generated changes, or ask Arceus to create the first task.</p>
      </div>
    </div>
  );
}
