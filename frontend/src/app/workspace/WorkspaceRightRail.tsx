import { AppWindow, ChevronLeft, ChevronRight, FileDiff, FolderTree, GitPullRequest, ListChecks, Network, Play, Terminal, Workflow } from 'lucide-react';
import type { AgentJob, PreviewCheck, TerminalSession } from './ActivityPanel';
import styles from './Workspace.module.css';
import type { WorkspaceRightPanelView } from './workspacePageUtils';
import type { WorkspaceSuggestion } from './workspaceSuggestions';

type WorkspaceRightRailProps = {
  rightPanelOpen: boolean;
  rightPanelView: WorkspaceRightPanelView;
  terminalPanelOpen: boolean;
  visibleFileCount: number;
  terminalSessions: Record<string, TerminalSession>;
  patchPreviewCount: number;
  jobs: AgentJob[];
  previewChecks: PreviewCheck[];
  workspaceTasks: WorkspaceSuggestion[];
  onOpenRightTool: (view: WorkspaceRightPanelView) => void;
  onToggleTerminal: () => void;
  onToggleRightPanel: () => void;
};

export default function WorkspaceRightRail({
  rightPanelOpen,
  rightPanelView,
  terminalPanelOpen,
  visibleFileCount,
  terminalSessions,
  patchPreviewCount,
  jobs,
  previewChecks,
  workspaceTasks,
  onOpenRightTool,
  onToggleTerminal,
  onToggleRightPanel,
}: WorkspaceRightRailProps) {
  const terminalCount = Object.keys(terminalSessions).length;

  return (
    <div className={styles.rightRail}>
      <button
        className={rightPanelOpen && rightPanelView === 'explorer' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Folder structure"
        onClick={() => onOpenRightTool('explorer')}
      >
        <FolderTree size={14} />
        {visibleFileCount > 0 && <span className={styles.railBadge}>{Math.min(visibleFileCount, 99)}</span>}
      </button>
      <button
        className={terminalPanelOpen ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title={terminalPanelOpen ? 'Hide terminal' : 'Open terminal'}
        onClick={onToggleTerminal}
      >
        <Terminal size={14} />
        {terminalCount > 0 && <span className={styles.railBadge}>{terminalCount}</span>}
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'org' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Engineering organization"
        onClick={() => onOpenRightTool('org')}
      >
        <Network size={14} />
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'changes' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Changes"
        onClick={() => onOpenRightTool('changes')}
      >
        <FileDiff size={14} />
        {patchPreviewCount > 0 && <span className={styles.railBadge}>{Math.min(patchPreviewCount, 9)}</span>}
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'jobs' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Jobs"
        onClick={() => onOpenRightTool('jobs')}
      >
        <Workflow size={14} />
        {jobs.some((job) => ['running', 'queued', 'failed', 'timeout'].includes(job.status || '')) && <span className={styles.railDot} />}
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'preview' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Preview"
        onClick={() => onOpenRightTool('preview')}
      >
        <Play size={14} />
        {previewChecks.some((check) => check.status !== 'passed') && <span className={styles.railDot} />}
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'git' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Git / PR"
        onClick={() => onOpenRightTool('git')}
      >
        <GitPullRequest size={14} />
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'apps' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Apps / Connectors"
        onClick={() => onOpenRightTool('apps')}
      >
        <AppWindow size={14} />
      </button>
      <button
        className={rightPanelOpen && rightPanelView === 'tasks' ? styles.rightRailButtonActive : styles.rightRailButton}
        type="button"
        title="Suggested Tasks"
        onClick={() => onOpenRightTool('tasks')}
      >
        <ListChecks size={14} />
        {workspaceTasks.length > 0 && <span className={styles.railBadge}>{Math.min(workspaceTasks.length, 9)}</span>}
      </button>
      <button
        className={styles.rightRailButton}
        type="button"
        title={rightPanelOpen ? 'Hide right panel' : 'Show right panel'}
        onClick={onToggleRightPanel}
      >
        {rightPanelOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </div>
  );
}
