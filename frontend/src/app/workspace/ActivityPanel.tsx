'use client';

import { useEffect, useState } from 'react';
import { Check, CircleDot, Eye, FileCode2, FilePenLine, Rocket, Search, Sparkles, Terminal, X } from 'lucide-react';
import DiffViewer from './DiffViewer';
import PreviewPanel from './PreviewPanel';
import GitPanel, { type GitDeliveryPackage } from './GitPanel';
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
  logs?: Array<{ kind: string; message: string; detail?: string; timestamp?: string }>;
  files_touched?: Array<{ filename?: string; file_id?: string }>;
  commands_run?: Array<{ command?: string; status?: string; return_code?: number | null; provider?: string; duration_ms?: number } | string>;
  result?: Record<string, any>;
  metadata?: Record<string, any>;
  progress?: { stage?: string; detail?: string; percent?: number; updated_at?: string };
  heartbeat_at?: string | null;
  retry_count?: number;
  worker_id?: string | null;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
};

export type WorkerStatus = {
  enabled?: boolean;
  alive?: boolean;
  backend?: string;
  celery_enabled?: boolean;
  celery_workers?: string[];
  worker_id?: string;
  queued_jobs?: number;
  claimed_jobs?: number;
  running_jobs?: number;
  cancel_requested_jobs?: number;
  interrupted_jobs?: number;
  poll_seconds?: number;
  job_timeout_seconds?: number;
  job_stale_seconds?: number;
  max_retries?: number;
};

export type PatchPreviewItem = {
  operation_id?: string;
  operation?: 'create' | 'modify' | 'delete' | 'rename' | 'folder' | string;
  file_id: string;
  filename: string;
  new_filename?: string;
  diff: string;
  additions?: number;
  deletions?: number;
  conflict?: boolean;
  base_checksum?: string;
  current_checksum?: string;
  status?: string;
  hunks?: Array<{
    id: string;
    index: number;
    header?: string;
    status?: string;
    additions?: number;
    deletions?: number;
    lines?: string[];
    old_lines?: string[];
    new_lines?: string[];
  }>;
};

export type WorkspaceCommand = {
  label: string;
  command: string;
  source?: string;
  script?: string;
};

export type GitHubRepository = {
  id?: number | string;
  full_name: string;
  default_branch?: string;
  private?: boolean;
  html_url?: string;
};

export type GitHubBranch = {
  name: string;
  sha?: string;
  protected?: boolean;
};

export type GitHubStatus = {
  configured?: boolean;
  connected?: boolean;
  app_name?: string;
  account?: { login?: string; type?: string; avatar_url?: string };
  repositories?: GitHubRepository[];
  selected_repo?: string;
  working_branch?: string;
  latest_commit_sha?: string;
  pull_request_url?: string;
  checks?: Array<{ name?: string; status?: string; conclusion?: string; html_url?: string }>;
  check_summary?: { total?: number; passed?: number; failed?: number; running?: number };
  staged?: {
    staged?: Array<{ filename?: string; operation?: string; additions?: number; deletions?: number }>;
    count?: number;
    approval_state?: string;
    commit_ready?: boolean;
    commit_blockers?: Array<{ code?: string; message?: string; cause?: string; files?: string[]; pending_files?: string[] }>;
    line_impact?: { additions?: number; deletions?: number };
    last_applied_at?: string;
  };
};

export type RuntimeStatus = {
  provider?: string;
  status?: string;
  production?: boolean;
  local_allowed?: boolean;
  e2b_configured?: boolean;
  root_exists?: boolean;
  last_synced_at?: string;
  files_written?: number;
  files_skipped?: number;
  managed_paths?: number;
  install_state?: string;
  last_heartbeat_at?: string;
  last_command?: {
    command?: string;
    status?: string;
    return_code?: number | null;
    provider?: string;
    duration_ms?: number;
    output_excerpt?: string;
  };
  preview?: {
    status?: string;
    preview_url?: string;
    command?: string;
  };
};

export type TerminalSession = {
  id: string;
  status?: string;
  cwd?: string;
  backend?: string;
  history?: string[];
  logs?: Array<Record<string, any> | string>;
  created_at?: string;
  updated_at?: string;
};

export type PreviewLogs = {
  logs?: string;
  issues?: string[];
  excerpts?: string[];
  status?: string;
  command?: string;
  updated_at?: string;
};

export type PreviewCheck = {
  url: string;
  status: string;
  status_code?: number | null;
  title?: string;
  issues?: string[];
  checked_at?: string;
  content_type?: string;
  browser?: string;
  screenshot_path?: string;
  screenshot_url?: string;
  screenshot_base64?: string;
  html_snapshot_path?: string;
  html_snapshot_url?: string;
  artifacts?: Array<{ name?: string; path?: string; url?: string; kind?: string; size_bytes?: number; entropy?: number }>;
  console_errors?: Array<string | { type?: string; text?: string; args?: string[]; url?: string; line?: number; column?: number }>;
  page_errors?: string[];
  network_failures?: Array<{ url?: string; failure?: any; error?: string; method?: string; resource_type?: string }>;
  blank_page?: boolean;
  first_contentful_paint_ms?: number | null;
  playwright_error?: string;
  verification_report?: {
    browser?: string;
    blank_page?: boolean;
    first_contentful_paint_ms?: number | null;
    console_error_count?: number;
    page_error_count?: number;
    network_failure_count?: number;
  };
  fix_suggestion_prompt?: string;
};

export type WorkspaceAnalysis = {
  summary?: {
    files?: number;
    total_lines?: number;
    total_bytes?: number;
    languages?: Record<string, number>;
  };
  imports?: Array<{ filename: string; line: number; module: string }>;
  exports?: Array<{ filename: string; line: number; symbol: string }>;
  routes?: Array<{ filename: string; kind: string }>;
  components?: Array<{ filename: string; line: number; name: string }>;
  symbols?: Array<{ filename: string; line: number; name: string; kind: string }>;
  dependencies?: Record<string, string[]>;
  entrypoints?: Array<{ filename: string; kind: string }>;
  hotspots?: Array<{ filename: string; line: number; snippet: string }>;
  risk_files?: Array<{ filename: string; hotspots?: number; lines?: number; reason?: string; symbols?: string[] }>;
  analyzed_at?: string;
};

export type RollbackSnapshot = {
  snapshot_id: string;
  index?: number;
  applied_at?: string;
  summary?: string;
  file_count?: number;
  operation_types?: string[];
  impact?: {
    created_files?: string[];
    deleted_files?: string[];
    renamed_files?: Array<{ from?: string; to?: string }>;
    folders_created?: string[];
  };
  files?: Array<{ file_id?: string; filename?: string; operation?: string }>;
};

type Props = {
  events: ActivityEvent[];
  jobs: AgentJob[];
  workerStatus?: WorkerStatus | null;
  patchPreview: PatchPreviewItem[];
  commands: WorkspaceCommand[];
  runtimeStatus: RuntimeStatus | null;
  githubStatus: GitHubStatus | null;
  githubRepositories: GitHubRepository[];
  githubBranches?: GitHubBranch[];
  selectedGithubRepo: string;
  deliveryPackage?: GitDeliveryPackage | null;
  analysis: WorkspaceAnalysis | null;
  rollbackSnapshots: RollbackSnapshot[];
  hasPatch: boolean;
  canApply: boolean;
  onApply: () => void;
  onReject: () => void;
  onApplySelection: (selection: { fileIds?: string[]; operationIds?: string[]; hunkIds?: string[] }) => void;
  onRejectSelection: (selection: { fileIds?: string[]; operationIds?: string[] }) => void;
  onApproveHunk: (hunkId: string) => void;
  onRejectHunk: (hunkId: string) => void;
  onResetPatchReview: () => void;
  onRollback: () => void;
  onRollbackSnapshot: (snapshotId: string) => void;
  onLoadRollbackSnapshots: () => void;
  canRunCommand: boolean;
  onRunCommand: (command: string) => void;
  onRunChecks: () => void;
  onInstallRuntime: () => void;
  onRefreshJobs: () => void;
  onCancelJob: (jobId: string) => void;
  onPauseJob: (jobId: string) => void;
  onResumeJob: (jobId: string) => void;
  onRetryJob: (jobId: string) => void;
  terminalSessions: TerminalSession[];
  activeTerminalId: string;
  terminalCommand: string;
  onCreateTerminal: () => void;
  onSelectTerminal: (terminalId: string) => void;
  onTerminalCommandChange: (value: string) => void;
  onSendTerminalInput: () => void;
  onKillTerminal: (terminalId: string) => void;
  canUseTerminal: boolean;
  onSyncRuntime: () => void;
  onAnalyzeWorkspace: () => void;
  previewUrl: string;
  previewChecks: PreviewCheck[];
  onPreviewUrlChange: (value: string) => void;
  onCheckPreview: () => void;
  canCheckPreview: boolean;
  onFixPreview: (instruction?: string) => void;
  canFixPreview: boolean;
  onStartPreview: () => void;
  onStopPreview: () => void;
  onLoadPreviewLogs: () => void;
  canStartPreview: boolean;
  previewLogs: PreviewLogs | null;
  repoUrl: string;
  githubBaseBranch: string;
  githubBranchName: string;
  onRepoUrlChange: (value: string) => void;
  onGithubRepoChange: (value: string) => void;
  onGithubBaseBranchChange: (value: string) => void;
  onGithubBranchNameChange: (value: string) => void;
  onConnectGithubApp: () => void;
  onRefreshGithub: () => void;
  onCreateGithubBranch: () => void;
  onCommitGithubChanges: (message?: string, filenames?: string[]) => void;
  onCheckGithubPrStatus: () => void;
  onConnectRepo: () => void;
  onImportRepo: () => void;
  onPreparePr: () => void;
  onOpenPr: (title?: string, body?: string) => void;
  onCommitAndOpenPr: (payload: { commit_message?: string; title?: string; body?: string; branch_name?: string; filenames?: string[] }) => void;
  canUseGit: boolean;
  initialTab?: ActivityTab;
  onClose?: () => void;
  showTabs?: boolean;
  terminalHelp?: string;
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

function diffStats(diff: string) {
  return diff.split('\n').reduce(
    (stats, line) => {
      if (line.startsWith('+') && !line.startsWith('+++')) stats.additions += 1;
      if (line.startsWith('-') && !line.startsWith('---')) stats.deletions += 1;
      return stats;
    },
    { additions: 0, deletions: 0 }
  );
}

const commands: WorkspaceCommand[] = [
  { label: 'Build', command: 'npm run build' },
  { label: 'Test', command: 'npm test' },
  { label: 'Lint', command: 'npm run lint' },
  { label: 'Typecheck', command: 'npm run typecheck' },
];

type ActivityTab = 'changes' | 'jobs' | 'terminal' | 'preview' | 'git' | 'checks' | 'rollback';

const tabs: Array<{ id: ActivityTab; label: string }> = [
  { id: 'changes', label: 'Changes' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'terminal', label: 'Terminal' },
  { id: 'preview', label: 'Preview' },
  { id: 'git', label: 'Git' },
  { id: 'checks', label: 'Checks' },
  { id: 'rollback', label: 'Rollback' },
];

function operationLabel(operation?: string) {
  switch ((operation || 'modify').toLowerCase()) {
    case 'create':
      return 'Create file';
    case 'delete':
      return 'Delete file';
    case 'rename':
      return 'Rename';
    case 'folder':
      return 'Create folder';
    default:
      return 'Modify';
  }
}

function operationTone(operation?: string) {
  switch ((operation || 'modify').toLowerCase()) {
    case 'create':
    case 'folder':
      return styles.reviewBadgeCreate;
    case 'delete':
      return styles.reviewBadgeDelete;
    case 'rename':
      return styles.reviewBadgeRename;
    default:
      return styles.reviewBadgeModify;
  }
}

export default function ActivityPanel({
  events,
  jobs,
  workerStatus,
  patchPreview,
  commands: workspaceCommands,
  runtimeStatus,
  githubStatus,
  githubRepositories,
  githubBranches,
  selectedGithubRepo,
  deliveryPackage,
  analysis,
  rollbackSnapshots,
  hasPatch,
  canApply,
  onApply,
  onReject,
  onApplySelection,
  onRejectSelection,
  onApproveHunk,
  onRejectHunk,
  onResetPatchReview,
  onRollback,
  onRollbackSnapshot,
  onLoadRollbackSnapshots,
  canRunCommand,
  onRunCommand,
  onRunChecks,
  onInstallRuntime,
  onRefreshJobs,
  onCancelJob,
  onPauseJob,
  onResumeJob,
  onRetryJob,
  terminalSessions,
  activeTerminalId,
  terminalCommand,
  onCreateTerminal,
  onSelectTerminal,
  onTerminalCommandChange,
  onSendTerminalInput,
  onKillTerminal,
  canUseTerminal,
  onSyncRuntime,
  onAnalyzeWorkspace,
  previewUrl,
  previewChecks,
  onPreviewUrlChange,
  onCheckPreview,
  canCheckPreview,
  onFixPreview,
  canFixPreview,
  onStartPreview,
  onStopPreview,
  onLoadPreviewLogs,
  canStartPreview,
  previewLogs,
  repoUrl,
  githubBaseBranch,
  githubBranchName,
  onRepoUrlChange,
  onGithubRepoChange,
  onGithubBaseBranchChange,
  onGithubBranchNameChange,
  onConnectGithubApp,
  onRefreshGithub,
  onCreateGithubBranch,
  onCommitGithubChanges,
  onCheckGithubPrStatus,
  onConnectRepo,
  onImportRepo,
  onPreparePr,
  onOpenPr,
  onCommitAndOpenPr,
  canUseGit,
  initialTab = 'changes',
  onClose,
  showTabs = true,
  terminalHelp,
}: Props) {
  const [activeTab, setActiveTab] = useState<ActivityTab>(initialTab);
  const [selectedPatchFileId, setSelectedPatchFileId] = useState('');
  const commandButtons = workspaceCommands.length ? workspaceCommands : commands;
  const patchKey = (item: PatchPreviewItem) => item.operation_id || item.file_id || item.filename;
  const selectedPatch = patchPreview.find((item) => patchKey(item) === selectedPatchFileId) || patchPreview[0] || null;
  const allPatchHunksRejected = patchPreview.length > 0 && patchPreview.every((item) => {
    if (!item.hunks?.length) return false;
    return item.hunks.every((hunk) => hunk.status === 'rejected');
  });
  const activeTerminal = terminalSessions.find((terminal) => terminal.id === activeTerminalId) || terminalSessions[0] || null;
  const activeLabel = tabs.find((tab) => tab.id === activeTab)?.label || 'Workspace';

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  return (
    <aside className={styles.activity}>
      <div className={styles.panelHeader}>
        <span>{activeLabel}</span>
        <div className={styles.panelHeaderActions}>
          <Eye size={14} />
          {onClose && (
            <button className={styles.panelIconButton} type="button" onClick={onClose} title="Hide panel">
              <X size={13} />
            </button>
          )}
        </div>
      </div>
      {showTabs && (
        <div className={styles.activityTabs}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={activeTab === tab.id ? styles.activityTabActive : styles.activityTab}
              type="button"
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
              {tab.id === 'changes' && patchPreview.length > 0 && <strong>{patchPreview.length}</strong>}
              {tab.id === 'jobs' && jobs.length > 0 && <strong>{jobs.length}</strong>}
              {tab.id === 'terminal' && terminalSessions.length > 0 && <strong>{terminalSessions.length}</strong>}
              {tab.id === 'rollback' && rollbackSnapshots.length > 0 && <strong>{rollbackSnapshots.length}</strong>}
            </button>
          ))}
        </div>
      )}
      <div className={styles.activityList}>
        {activeTab === 'changes' && (
          <div className={styles.changesPanel}>
            <div className={styles.changesHeader}>
              <span>{patchPreview.length ? 'Review Required' : 'Changes'}</span>
              <strong>{patchPreview.length}</strong>
            </div>
            {patchPreview.length === 0 && <div className={styles.meta}>No review-required changes. Safe edits apply automatically and can be undone from the chat receipt.</div>}
            {patchPreview.length > 0 && (
              <>
                <div className={styles.reviewSummary}>
                  <span>{patchPreview.reduce((total, item) => total + (item.additions || diffStats(item.diff || '').additions), 0)} added</span>
                  <span>{patchPreview.reduce((total, item) => total + (item.deletions || diffStats(item.diff || '').deletions), 0)} removed</span>
                </div>
                <div className={styles.reviewFileList}>
                  {patchPreview.map((item) => {
                    const stats = diffStats(item.diff || '');
                    const active = selectedPatch ? patchKey(selectedPatch) === patchKey(item) : false;
                    const operation = item.operation || 'modify';
                    const hunkCount = item.hunks?.length || 0;
                    return (
                      <button
                        key={patchKey(item)}
                        className={active ? styles.reviewFileActive : styles.reviewFile}
                        type="button"
                        onClick={() => setSelectedPatchFileId(patchKey(item))}
                      >
                        <span><FileCode2 size={14} /> {item.new_filename || item.filename}</span>
                        <em>
                          <small className={`${styles.reviewBadge} ${operationTone(operation)}`}>{operationLabel(operation)}</small>
                          {item.conflict && <small className={`${styles.reviewBadge} ${styles.reviewBadgeConflict}`}>Conflict</small>}
                          {item.status && <small className={styles.reviewBadge}>{item.status}</small>}
                          {hunkCount ? ` ${hunkCount} hunk${hunkCount === 1 ? '' : 's'} · ` : ' '}
                          +{item.additions || stats.additions} / -{item.deletions || stats.deletions}
                        </em>
                      </button>
                    );
                  })}
                </div>
                {selectedPatch && (
                  <div className={styles.reviewDetail}>
                    <DiffViewer
                      patch={selectedPatch}
                      canApply={canApply}
                      hasPatch={hasPatch}
                      onApplySelection={onApplySelection}
                      onRejectSelection={onRejectSelection}
                      onApproveHunk={onApproveHunk}
                      onRejectHunk={onRejectHunk}
                      onResetPatchReview={onResetPatchReview}
                    />
                  </div>
                )}
              </>
            )}
            {patchPreview.length > 0 && (
              <div className={styles.tabActionStack}>
                <button className={styles.approveButton} type="button" onClick={onApply} disabled={!canApply || allPatchHunksRejected} title={allPatchHunksRejected ? 'All hunks rejected' : undefined}>
                  <Check size={15} /> Apply reviewed changes
                </button>
                <button className={styles.rejectButton} type="button" onClick={onReject} disabled={!hasPatch}>
                  <X size={15} /> Remove from review
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'checks' && (
          <div className={styles.analysisPanel}>
            <div className={styles.runtimePanel}>
              <div className={styles.changesHeader}>
                <span>Runtime</span>
                <strong>{runtimeStatus?.status || 'not synced'}</strong>
              </div>
              <div className={styles.runtimeGrid}>
                <span>Provider</span>
                <strong>{runtimeStatus?.provider || 'unknown'}</strong>
                <span>Mode</span>
                <strong>{runtimeStatus?.production ? 'production' : 'development'}</strong>
                <span>Files</span>
                <strong>{runtimeStatus?.files_written ?? 0} synced</strong>
                <span>Install</span>
                <strong>{runtimeStatus?.install_state || 'not installed'}</strong>
                <span>Preview</span>
                <strong>{runtimeStatus?.preview?.status || 'stopped'}</strong>
              </div>
              {runtimeStatus?.provider === 'local' && !runtimeStatus.local_allowed && (
                <div className={styles.policyWarning}>Local subprocess execution is disabled for this environment.</div>
              )}
              {runtimeStatus?.provider === 'e2b' && runtimeStatus.e2b_configured === false && (
                <div className={styles.policyWarning}>E2B is selected but no API key is configured.</div>
              )}
              {runtimeStatus?.last_command && (
                <div className={styles.lastCommand}>
                  <strong>{runtimeStatus.last_command.command}</strong>
                  <span>{runtimeStatus.last_command.status} via {runtimeStatus.last_command.provider || runtimeStatus.provider} {runtimeStatus.last_command.duration_ms ? `· ${runtimeStatus.last_command.duration_ms}ms` : ''}</span>
                  {runtimeStatus.last_command.output_excerpt && <em>{runtimeStatus.last_command.output_excerpt}</em>}
                </div>
              )}
              <button className={styles.fullWidthButton} type="button" onClick={onInstallRuntime} disabled={!canRunCommand}>
                Install dependencies
              </button>
            </div>
            <div className={styles.changesHeader}>
              <span>Workspace Map</span>
              <strong>{analysis?.summary?.files || 0}</strong>
            </div>
            <button className={styles.fullWidthButton} type="button" onClick={onAnalyzeWorkspace} disabled={!canRunCommand}>
              Analyze Workspace
            </button>
            <button className={styles.fullWidthButton} type="button" onClick={onSyncRuntime} disabled={!canRunCommand}>
              Sync Runtime
            </button>
            <button className={styles.fullWidthButton} type="button" onClick={onRunChecks} disabled={!canRunCommand}>
              Run all checks
            </button>
            <div className={styles.commandGrid}>
              {commandButtons.map((item) => (
                <button key={item.command} className={styles.commandButton} type="button" title={item.script || item.source || item.command} onClick={() => onRunCommand(item.command)} disabled={!canRunCommand}>
                  {item.label}
                </button>
              ))}
            </div>
            {!analysis && <div className={styles.meta}>Run analysis or checks to map the current workspace.</div>}
            {analysis && (
              <>
            <div className={styles.analysisGrid}>
              <span>{analysis.summary?.total_lines || 0} lines</span>
              <span>{Object.keys(analysis.summary?.languages || {}).length} languages</span>
              <span>{analysis.imports?.length || 0} imports</span>
              <span>{analysis.symbols?.length || 0} symbols</span>
              <span>{analysis.hotspots?.length || 0} hotspots</span>
            </div>
            {Object.entries(analysis.summary?.languages || {}).slice(0, 6).map(([language, count]) => (
              <div className={styles.contextLine} key={language}>
                <strong>{language}</strong>
                <span>{count} file(s)</span>
              </div>
            ))}
            {(analysis.routes || []).slice(0, 3).map((route) => (
              <div className={styles.contextMemory} key={route.filename}>Route: {route.filename}</div>
            ))}
            {(analysis.entrypoints || []).slice(0, 4).map((entry) => (
              <div className={styles.contextMemory} key={`entry-${entry.filename}`}>Entrypoint: {entry.filename}</div>
            ))}
            {(analysis.components || []).slice(0, 3).map((component) => (
              <div className={styles.contextMemory} key={`${component.filename}-${component.line}`}>Component: {component.name} in {component.filename}</div>
            ))}
            {(analysis.symbols || []).slice(0, 6).map((symbol) => (
              <div className={styles.contextLine} key={`${symbol.filename}-${symbol.line}-${symbol.name}`}>
                <strong>{symbol.name}</strong>
                <span>{symbol.kind} · {symbol.filename}:{symbol.line}</span>
              </div>
            ))}
            {Object.entries(analysis.dependencies || {}).slice(0, 5).map(([filename, deps]) => (
              <div className={styles.contextMemory} key={`deps-${filename}`}>
                Depends: {filename} {'->'} {deps.slice(0, 4).join(', ')}
              </div>
            ))}
            {(analysis.risk_files || []).slice(0, 4).map((file) => (
              <div className={styles.hotspotLine} key={`risk-${file.filename}`}>
                Risk: {file.filename} · {file.reason} · {file.hotspots || 0} hotspot(s) · {file.lines || 0} lines
              </div>
            ))}
            {(analysis.hotspots || []).slice(0, 3).map((hotspot) => (
              <div className={styles.hotspotLine} key={`${hotspot.filename}-${hotspot.line}`}>{hotspot.filename}:{hotspot.line} {hotspot.snippet}</div>
            ))}
              </>
            )}
          </div>
        )}

        {activeTab === 'rollback' && (
          <div className={styles.rollbackPanel}>
          <div className={styles.changesHeader}>
            <span>Rollback History</span>
            <strong>{rollbackSnapshots.length}</strong>
          </div>
          <button className={styles.fullWidthButton} type="button" onClick={onLoadRollbackSnapshots} disabled={!canRunCommand}>
            Refresh rollback history
          </button>
          {rollbackSnapshots.slice(0, 5).map((snapshot) => (
            <div className={styles.rollbackItem} key={snapshot.snapshot_id}>
              <div>
                <strong>{snapshot.summary || 'Applied patch'}</strong>
                <span>
                  {(snapshot.operation_types || ['modify']).join(', ')} · {snapshot.file_count || snapshot.files?.length || 0} item(s)
                  {snapshot.applied_at ? ` - ${new Date(snapshot.applied_at).toLocaleString()}` : ''}
                </span>
                {(snapshot.impact?.created_files?.length || snapshot.impact?.deleted_files?.length || snapshot.impact?.renamed_files?.length || snapshot.impact?.folders_created?.length) ? (
                  <em>
                    {(snapshot.impact?.created_files?.length || 0)} created · {(snapshot.impact?.deleted_files?.length || 0)} deleted · {(snapshot.impact?.renamed_files?.length || 0)} renamed · {(snapshot.impact?.folders_created?.length || 0)} folders
                  </em>
                ) : null}
                {!!snapshot.files?.length && (
                  <div className={styles.rollbackFiles}>
                    {snapshot.files.slice(0, 4).map((file) => (
                      <small key={`${snapshot.snapshot_id}-${file.file_id || file.filename}`}>
                        {operationLabel(file.operation)} · {file.filename}
                      </small>
                    ))}
                    {snapshot.files.length > 4 && <small>+{snapshot.files.length - 4} more</small>}
                  </div>
                )}
              </div>
              <button type="button" onClick={() => onRollbackSnapshot(snapshot.snapshot_id)} disabled={!canRunCommand}>
                Restore
              </button>
            </div>
          ))}
          {rollbackSnapshots.length === 0 && <div className={styles.meta}>No applied patch snapshots yet.</div>}
          <button className={styles.rejectButton} type="button" onClick={onRollback} disabled={!canRunCommand}>
            Rollback last apply
          </button>
        </div>
        )}

        {activeTab === 'preview' && (
          <PreviewPanel
            previewUrl={previewUrl}
            previewChecks={previewChecks}
            previewLogs={previewLogs}
            canCheckPreview={canCheckPreview}
            canFixPreview={canFixPreview}
            canStartPreview={canStartPreview}
            onPreviewUrlChange={onPreviewUrlChange}
            onCheckPreview={onCheckPreview}
            onFixPreview={onFixPreview}
            onStartPreview={onStartPreview}
            onStopPreview={onStopPreview}
            onLoadPreviewLogs={onLoadPreviewLogs}
          />
        )}

        {activeTab === 'git' && (
          <GitPanel
            githubStatus={githubStatus}
            githubRepositories={githubRepositories}
            githubBranches={githubBranches || []}
            selectedGithubRepo={selectedGithubRepo}
            githubBaseBranch={githubBaseBranch}
            githubBranchName={githubBranchName}
            patchPreview={patchPreview}
            deliveryPackage={deliveryPackage}
            canUseGit={canUseGit}
            busy={false}
            onGithubRepoChange={onGithubRepoChange}
            onGithubBaseBranchChange={onGithubBaseBranchChange}
            onGithubBranchNameChange={onGithubBranchNameChange}
            onConnectGithubApp={onConnectGithubApp}
            onRefreshGithub={onRefreshGithub}
            onImportRepo={onImportRepo}
            onCreateGithubBranch={onCreateGithubBranch}
            onCommitGithubChanges={onCommitGithubChanges}
            onOpenPr={onOpenPr}
            onCommitAndOpenPr={onCommitAndOpenPr}
            onCheckGithubPrStatus={onCheckGithubPrStatus}
          />
        )}

        {activeTab === 'jobs' && (
          <div className={styles.jobStack}>
            <div className={styles.changesHeader}>
              <span>Durable Jobs</span>
              <strong>{jobs.length}</strong>
            </div>
            <div className={styles.workerHealthCard}>
              <div>
                <span>{workerStatus?.alive ? 'Worker online' : workerStatus?.enabled === false ? 'Worker disabled' : 'Worker offline'}</span>
                <strong>{workerStatus?.backend || 'worker'} · {workerStatus?.celery_workers?.[0] || workerStatus?.worker_id || 'unassigned'}</strong>
              </div>
              <div>
                <small>{workerStatus?.queued_jobs || 0} queued</small>
                <small>{workerStatus?.claimed_jobs || 0} claimed</small>
                <small>{workerStatus?.running_jobs || 0} running</small>
                <small>{workerStatus?.cancel_requested_jobs || 0} cancelling</small>
                <small>{workerStatus?.interrupted_jobs || 0} failed</small>
              </div>
            </div>
            <button className={styles.fullWidthButton} type="button" onClick={onRefreshJobs}>
              Refresh jobs
            </button>
            {jobs.length === 0 && <div className={styles.meta}>No durable jobs yet.</div>}
            {jobs.slice(0, 8).map((job) => {
              const running = ['queued', 'retrying', 'claimed', 'running', 'cancel_requested'].includes(job.status);
              const paused = job.status === 'paused';
              const failed = ['failed', 'cancelled', 'timeout', 'blocked', 'interrupted', 'dead_letter'].includes(job.status);
              const retryable = failed && job.mode?.startsWith('background_');
              const statusClass = running ? styles.jobStatusRunning : failed ? styles.jobStatusError : styles.jobStatusDone;
              return (
              <details className={styles.jobDetail} key={job.id}>
                <summary>
                  <span>{job.mode}</span>
                  <strong className={statusClass}>{job.status}</strong>
                </summary>
                {job.prompt && <p>{job.prompt}</p>}
                {job.progress && (
                  <div className={styles.jobProgress}>
                    <div>
                      <span>{job.progress.stage || job.status}</span>
                      <strong>{typeof job.progress.percent === 'number' ? `${job.progress.percent}%` : 'active'}</strong>
                    </div>
                    <div className={styles.jobProgressTrack}>
                      <span style={{ width: `${Math.max(0, Math.min(100, Number(job.progress.percent || 0)))}%` }} />
                    </div>
                    {job.progress.detail && <em>{job.progress.detail}</em>}
                  </div>
                )}
                <div className={styles.jobMetaLine}>
                  Started: {job.started_at ? new Date(job.started_at).toLocaleTimeString() : 'not started'}
                  {job.completed_at ? ` - Finished: ${new Date(job.completed_at).toLocaleTimeString()}` : ''}
                </div>
                <div className={styles.jobMetaLine}>
                  Worker: {job.worker_id || 'unassigned'} {job.retry_count ? `- Retry ${job.retry_count}` : ''}
                  {job.heartbeat_at ? ` - Heartbeat ${new Date(job.heartbeat_at).toLocaleTimeString()}` : ''}
                </div>
                {(job.logs || []).slice(-6).map((log, index) => (
                  <div className={styles.jobLogLine} key={`${job.id}-log-${index}`}>
                    <span>{log.kind}</span>
                    <strong>{log.message}</strong>
                    {log.detail && <em>{log.detail}</em>}
                  </div>
                ))}
                {(job.files_touched || []).length > 0 && (
                  <div className={styles.jobMetaLine}>
                    Files: {(job.files_touched || []).map((file) => file.filename || file.file_id).filter(Boolean).join(', ')}
                  </div>
                )}
                {(job.commands_run || []).length > 0 && (
                  <div className={styles.jobMetaLine}>
                    Commands: {(job.commands_run || []).map((command) => {
                      if (typeof command === 'string') return command;
                      const timing = typeof command.duration_ms === 'number' ? ` ${command.duration_ms}ms` : '';
                      const provider = command.provider ? ` via ${command.provider}` : '';
                      return `${command.command || 'command'}${provider}${timing}`;
                    }).filter(Boolean).join(', ')}
                  </div>
                )}
                {running && (
                  <div className={styles.previewButtonRow}>
                    <button className={styles.fullWidthButton} type="button" onClick={() => onPauseJob(job.id)}>
                      Pause
                    </button>
                    <button className={styles.rejectButton} type="button" onClick={() => onCancelJob(job.id)}>
                      Cancel job
                    </button>
                  </div>
                )}
                {paused && (
                  <div className={styles.previewButtonRow}>
                    <button className={styles.fullWidthButton} type="button" onClick={() => onResumeJob(job.id)}>
                      Resume
                    </button>
                    <button className={styles.rejectButton} type="button" onClick={() => onCancelJob(job.id)}>
                      Cancel job
                    </button>
                  </div>
                )}
                {retryable && (
                  <button className={styles.fullWidthButton} type="button" onClick={() => onRetryJob(job.id)}>
                    Retry background job
                  </button>
                )}
              </details>
              );
            })}
          </div>
        )}

        {activeTab === 'terminal' && (
          <div className={styles.previewPanel}>
            <div className={styles.changesHeader}>
              <span>Terminal</span>
              <strong>{activeTerminal?.status || 'idle'}</strong>
            </div>
            <button className={styles.fullWidthButton} type="button" onClick={onCreateTerminal} disabled={!canUseTerminal}>
              <Terminal size={14} /> New terminal
            </button>
            {terminalHelp && <div className={styles.meta}>{terminalHelp}</div>}
            {terminalSessions.length > 0 && (
              <div className={styles.previewButtonRow}>
                {terminalSessions.slice(0, 4).map((terminal) => (
                  <button
                    key={terminal.id}
                    className={terminal.id === activeTerminal?.id ? styles.activityTabActive : styles.commandButton}
                    type="button"
                    title={terminal.cwd || terminal.id}
                    onClick={() => onSelectTerminal(terminal.id)}
                  >
                    {terminal.id.slice(0, 6)}
                  </button>
                ))}
              </div>
            )}
            {activeTerminal ? (
              <>
                <div className={styles.runtimeGrid}>
                  <span>CWD</span>
                  <strong title={activeTerminal.cwd || ''}>{activeTerminal.cwd || 'workspace runtime'}</strong>
                  <span>Status</span>
                  <strong>{activeTerminal.status || 'active'}</strong>
                  <span>Commands</span>
                  <strong>{activeTerminal.history?.length || 0}</strong>
                </div>
                <div className={styles.previewLogs}>
                  {(activeTerminal.logs || []).length === 0 && <div className={styles.meta}>No command output yet. Type a safe command below to run it in the workspace runtime.</div>}
                  {(activeTerminal.logs || []).slice(-8).map((log, index) => {
                    const logObject = typeof log === 'string' ? { output_excerpt: log } : log;
                    const output = logObject.output_excerpt || logObject.output || logObject.stderr || logObject.stdout || logObject.detail || '';
                    return (
                      <div className={styles.jobLogLine} key={`${activeTerminal.id}-terminal-${index}`}>
                        <span>{logObject.status || 'command'}</span>
                        <strong>{logObject.command || activeTerminal.history?.[index] || 'terminal'}</strong>
                        {typeof logObject.return_code === 'number' && <em>exit {logObject.return_code}</em>}
                        {output && <em>{String(output).slice(0, 900)}</em>}
                      </div>
                    );
                  })}
                </div>
                <div className={styles.previewInputRow}>
                  <input
                    className={styles.previewInput}
                    value={terminalCommand}
                    onChange={(event) => onTerminalCommandChange(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') onSendTerminalInput();
                    }}
                    placeholder="npm test, npm run build, git status..."
                  />
                  <button className={styles.commandButton} type="button" onClick={onSendTerminalInput} disabled={!canUseTerminal || !terminalCommand.trim()}>
                    Run
                  </button>
                </div>
                <button className={styles.rejectButton} type="button" onClick={() => onKillTerminal(activeTerminal.id)} disabled={!canUseTerminal || activeTerminal.status === 'killed'}>
                  Kill terminal
                </button>
              </>
            ) : (
              <div className={styles.meta}>Create a terminal to run safe workspace commands with logs tied to jobs and activity.</div>
            )}
          </div>
        )}

        <div className={styles.eventStack}>
          <div className={styles.meta}>Recent activity</div>
          {events.slice(0, 8).map((event) => (
            <div className={styles.activityItem} key={event.id}>
              <div className={styles.activityTitle}>
                <Icon kind={event.kind} />
                <span>{event.message}</span>
              </div>
              {event.detail && <div className={styles.activityDetail}>{event.detail}</div>}
              {event.diff && activeTab === 'changes' && <Diff diff={event.diff} />}
            </div>
          ))}
          {events.length === 0 && (
            <div className={styles.meta}>
              Activity appears here as Arceus reads files, researches, designs, edits, and prepares deployment steps.
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
