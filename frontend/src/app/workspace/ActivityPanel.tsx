'use client';

import { Check, CircleDot, Eye, FileCode2, FilePenLine, Rocket, Search, Sparkles, X } from 'lucide-react';
import styles from './Workspace.module.css';

export type ActivityEvent = {
  id: string;
  kind: 'start' | 'read' | 'code' | 'design' | 'deploy' | 'research' | 'edit' | 'done' | 'error';
  message: string;
  detail?: string;
  diff?: string;
};

export type AgentJob = {
  id: string;
  mode: string;
  status: string;
  approval_state?: string;
  prompt?: string;
  created_at?: string;
};

export type OSContext = {
  memories?: Array<{ id: string; type: string; content: string; importance?: number }>;
  goals?: Array<{ id: string; title: string; status: string; progress_pct?: number }>;
  tasks?: Array<{ id: string; title: string; status: string }>;
  schedules?: Array<{ id: string; title: string; next_run_at?: string }>;
  code_sessions?: Array<{ id: string; title: string; status: string }>;
  jobs?: Array<{ id: string; mode: string; status: string }>;
};

export type PatchPreviewItem = {
  file_id: string;
  filename: string;
  diff: string;
  additions?: number;
  deletions?: number;
};

export type WorkspaceCommand = {
  label: string;
  command: string;
  source?: string;
  script?: string;
};

type Props = {
  events: ActivityEvent[];
  jobs: AgentJob[];
  osContext: OSContext | null;
  patchPreview: PatchPreviewItem[];
  commands: WorkspaceCommand[];
  hasPatch: boolean;
  canApply: boolean;
  onApply: () => void;
  onReject: () => void;
  onApplyFile: (fileId: string) => void;
  onRejectFile: (fileId: string) => void;
  onRollback: () => void;
  canRunCommand: boolean;
  onRunCommand: (command: string) => void;
  onSyncRuntime: () => void;
  previewUrl: string;
  onPreviewUrlChange: (value: string) => void;
  onCheckPreview: () => void;
  canCheckPreview: boolean;
  onFixPreview: () => void;
  canFixPreview: boolean;
  repoUrl: string;
  onRepoUrlChange: (value: string) => void;
  onConnectRepo: () => void;
  onImportRepo: () => void;
  onPreparePr: () => void;
  onOpenPr: () => void;
  canUseGit: boolean;
};

function Icon({ kind }: { kind: ActivityEvent['kind'] }) {
  if (kind === 'research') return <Search size={15} />;
  if (kind === 'design') return <Sparkles size={15} />;
  if (kind === 'deploy') return <Rocket size={15} />;
  if (kind === 'edit' || kind === 'code') return <FilePenLine size={15} />;
  if (kind === 'done') return <Check size={15} />;
  if (kind === 'error') return <X size={15} />;
  return <CircleDot size={15} />;
}

function Diff({ diff }: { diff: string }) {
  return (
    <pre className={styles.diffBox}>
      {diff.split('\n').map((line, index) => (
        <span
          key={`${line}-${index}`}
          className={line.startsWith('+') ? styles.added : line.startsWith('-') ? styles.removed : undefined}
        >
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}

const commands: WorkspaceCommand[] = [
  { label: 'Build', command: 'npm run build' },
  { label: 'Test', command: 'npm test' },
  { label: 'Lint', command: 'npm run lint' },
  { label: 'Typecheck', command: 'npm run typecheck' },
];

export default function ActivityPanel({
  events,
  jobs,
  osContext,
  patchPreview,
  commands: workspaceCommands,
  hasPatch,
  canApply,
  onApply,
  onReject,
  onApplyFile,
  onRejectFile,
  onRollback,
  canRunCommand,
  onRunCommand,
  onSyncRuntime,
  previewUrl,
  onPreviewUrlChange,
  onCheckPreview,
  canCheckPreview,
  onFixPreview,
  canFixPreview,
  repoUrl,
  onRepoUrlChange,
  onConnectRepo,
  onImportRepo,
  onPreparePr,
  onOpenPr,
  canUseGit,
}: Props) {
  const commandButtons = workspaceCommands.length ? workspaceCommands : commands;
  return (
    <aside className={styles.activity}>
      <div className={styles.panelHeader}>
        <span>Activity / Changes</span>
        <Eye size={15} />
      </div>
      <div className={styles.activityList}>
        {patchPreview.length > 0 && (
          <div className={styles.changesPanel}>
            <div className={styles.changesHeader}>
              <span>Pending Changes</span>
              <strong>{patchPreview.length}</strong>
            </div>
            {patchPreview.map((item) => (
              <details className={styles.changeItem} key={item.file_id}>
                <summary>
                  <span><FileCode2 size={14} /> {item.filename}</span>
                  <em>+{item.additions || 0} / -{item.deletions || 0}</em>
                </summary>
                <Diff diff={item.diff} />
                <div className={styles.changeActions}>
                  <button type="button" onClick={() => onApplyFile(item.file_id)} disabled={!canApply}>
                    <Check size={14} /> Apply file
                  </button>
                  <button type="button" onClick={() => onRejectFile(item.file_id)} disabled={!hasPatch}>
                    <X size={14} /> Reject file
                  </button>
                </div>
              </details>
            ))}
          </div>
        )}
        {osContext && (
          <div className={styles.osContextPanel}>
            <div className={styles.meta}>NEXUS OS Context</div>
            <div className={styles.contextGrid}>
              <span>{osContext.goals?.length || 0} goals</span>
              <span>{osContext.tasks?.length || 0} tasks</span>
              <span>{osContext.memories?.length || 0} memories</span>
              <span>{osContext.jobs?.length || 0} jobs</span>
            </div>
            {(osContext.goals || []).slice(0, 2).map((goal) => (
              <div className={styles.contextLine} key={goal.id}>
                <strong>{goal.title}</strong>
                <span>{goal.status}</span>
              </div>
            ))}
            {(osContext.memories || []).slice(0, 2).map((memory) => (
              <div className={styles.contextMemory} key={memory.id}>{memory.content}</div>
            ))}
          </div>
        )}
        <div className={styles.previewPanel}>
          <div className={styles.meta}>Preview</div>
          <div className={styles.previewInputRow}>
            <input
              className={styles.previewInput}
              value={previewUrl}
              onChange={(event) => onPreviewUrlChange(event.target.value)}
              placeholder="https://your-preview-url.app"
            />
            <button className={styles.commandButton} type="button" onClick={onCheckPreview} disabled={!canCheckPreview}>
              Check
            </button>
          </div>
          <button className={styles.fullWidthButton} type="button" onClick={onFixPreview} disabled={!canFixPreview}>
            Fix preview issue
          </button>
          {previewUrl.trim() && (
            <iframe className={styles.previewFrame} src={previewUrl.trim()} title="Workspace preview" sandbox="allow-scripts allow-same-origin allow-forms" />
          )}
        </div>
        <div className={styles.previewPanel}>
          <div className={styles.meta}>Git / PR</div>
          <div className={styles.previewInputRow}>
            <input
              className={styles.previewInput}
              value={repoUrl}
              onChange={(event) => onRepoUrlChange(event.target.value)}
              placeholder="https://github.com/org/repo"
            />
            <button className={styles.commandButton} type="button" onClick={onConnectRepo} disabled={!canUseGit}>
              Connect
            </button>
          </div>
          <button className={styles.fullWidthButton} type="button" onClick={onImportRepo} disabled={!canUseGit}>
            Import repo files
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onPreparePr} disabled={!canUseGit}>
            Prepare PR
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onOpenPr} disabled={!canUseGit}>
            Open GitHub PR
          </button>
        </div>
        {jobs.length > 0 && (
          <div className={styles.jobStack}>
            <div className={styles.meta}>Durable jobs</div>
            {jobs.slice(0, 5).map((job) => (
              <div className={styles.jobItem} key={job.id}>
                <span>{job.mode}</span>
                <strong>{job.status}</strong>
              </div>
            ))}
          </div>
        )}
        {events.map((event) => (
          <div className={styles.activityItem} key={event.id}>
            <div className={styles.activityTitle}>
              <Icon kind={event.kind} />
              <span>{event.message}</span>
            </div>
            {event.detail && <div className={styles.activityDetail}>{event.detail}</div>}
            {event.diff && <Diff diff={event.diff} />}
          </div>
        ))}
        {events.length === 0 && (
          <div className={styles.meta}>
            Activity appears here as NEXUS reads files, researches, designs, edits, and prepares deployment steps.
          </div>
        )}
      </div>
      <div className={styles.activityFooter}>
        <button className={styles.fullWidthButton} type="button" onClick={onSyncRuntime} disabled={!canRunCommand}>
          Sync Runtime
        </button>
        <div className={styles.commandGrid}>
          {commandButtons.map((item) => (
            <button key={item.command} className={styles.commandButton} type="button" title={item.script || item.source || item.command} onClick={() => onRunCommand(item.command)} disabled={!canRunCommand}>
              {item.label}
            </button>
          ))}
        </div>
        <button className={styles.approveButton} type="button" onClick={onApply} disabled={!canApply}>
          <Check size={15} /> Approve all changes
        </button>
        <button className={styles.rejectButton} type="button" onClick={onReject} disabled={!hasPatch}>
          <X size={15} /> Reject changes
        </button>
        <button className={styles.rejectButton} type="button" onClick={onRollback} disabled={!canRunCommand}>
          Rollback last apply
        </button>
      </div>
    </aside>
  );
}
