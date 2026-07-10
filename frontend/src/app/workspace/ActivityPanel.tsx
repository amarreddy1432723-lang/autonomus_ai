'use client';

import { useState } from 'react';
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

export type GitHubRepository = {
  id?: number | string;
  full_name: string;
  default_branch?: string;
  private?: boolean;
  html_url?: string;
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
  files?: Array<{ file_id?: string; filename?: string }>;
};

type Props = {
  events: ActivityEvent[];
  jobs: AgentJob[];
  patchPreview: PatchPreviewItem[];
  commands: WorkspaceCommand[];
  runtimeStatus: RuntimeStatus | null;
  githubStatus: GitHubStatus | null;
  githubRepositories: GitHubRepository[];
  selectedGithubRepo: string;
  analysis: WorkspaceAnalysis | null;
  rollbackSnapshots: RollbackSnapshot[];
  hasPatch: boolean;
  canApply: boolean;
  onApply: () => void;
  onReject: () => void;
  onApplyFile: (fileId: string) => void;
  onRejectFile: (fileId: string) => void;
  onRollback: () => void;
  onRollbackSnapshot: (snapshotId: string) => void;
  onLoadRollbackSnapshots: () => void;
  canRunCommand: boolean;
  onRunCommand: (command: string) => void;
  onRunChecks: () => void;
  onInstallRuntime: () => void;
  onRefreshJobs: () => void;
  onCancelJob: (jobId: string) => void;
  onRetryJob: (jobId: string) => void;
  onSyncRuntime: () => void;
  onAnalyzeWorkspace: () => void;
  previewUrl: string;
  previewChecks: PreviewCheck[];
  onPreviewUrlChange: (value: string) => void;
  onCheckPreview: () => void;
  canCheckPreview: boolean;
  onFixPreview: () => void;
  canFixPreview: boolean;
  onStartPreview: () => void;
  onStopPreview: () => void;
  onLoadPreviewLogs: () => void;
  canStartPreview: boolean;
  previewLogs: PreviewLogs | null;
  repoUrl: string;
  githubBranchName: string;
  onRepoUrlChange: (value: string) => void;
  onGithubRepoChange: (value: string) => void;
  onGithubBranchNameChange: (value: string) => void;
  onConnectGithubApp: () => void;
  onRefreshGithub: () => void;
  onCreateGithubBranch: () => void;
  onCommitGithubChanges: () => void;
  onCheckGithubPrStatus: () => void;
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

type ActivityTab = 'changes' | 'jobs' | 'preview' | 'git' | 'checks' | 'rollback';

const tabs: Array<{ id: ActivityTab; label: string }> = [
  { id: 'changes', label: 'Changes' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'preview', label: 'Preview' },
  { id: 'git', label: 'Git' },
  { id: 'checks', label: 'Checks' },
  { id: 'rollback', label: 'Rollback' },
];

export default function ActivityPanel({
  events,
  jobs,
  patchPreview,
  commands: workspaceCommands,
  runtimeStatus,
  githubStatus,
  githubRepositories,
  selectedGithubRepo,
  analysis,
  rollbackSnapshots,
  hasPatch,
  canApply,
  onApply,
  onReject,
  onApplyFile,
  onRejectFile,
  onRollback,
  onRollbackSnapshot,
  onLoadRollbackSnapshots,
  canRunCommand,
  onRunCommand,
  onRunChecks,
  onInstallRuntime,
  onRefreshJobs,
  onCancelJob,
  onRetryJob,
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
  githubBranchName,
  onRepoUrlChange,
  onGithubRepoChange,
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
  canUseGit,
}: Props) {
  const [activeTab, setActiveTab] = useState<ActivityTab>('changes');
  const [selectedPatchFileId, setSelectedPatchFileId] = useState('');
  const commandButtons = workspaceCommands.length ? workspaceCommands : commands;
  const selectedPatch = patchPreview.find((item) => item.file_id === selectedPatchFileId) || patchPreview[0] || null;
  const selectedStats = selectedPatch ? diffStats(selectedPatch.diff || '') : { additions: 0, deletions: 0 };

  return (
    <aside className={styles.activity}>
      <div className={styles.panelHeader}>
        <span>Activity / Changes</span>
        <Eye size={15} />
      </div>
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
            {tab.id === 'rollback' && rollbackSnapshots.length > 0 && <strong>{rollbackSnapshots.length}</strong>}
          </button>
        ))}
      </div>
      <div className={styles.activityList}>
        {activeTab === 'changes' && (
          <div className={styles.changesPanel}>
            <div className={styles.changesHeader}>
              <span>Pending Changes</span>
              <strong>{patchPreview.length}</strong>
            </div>
            {patchPreview.length === 0 && <div className={styles.meta}>No pending changes. Ask NEXUS to edit code, then review diffs here.</div>}
            {patchPreview.length > 0 && (
              <>
                <div className={styles.reviewSummary}>
                  <span>{patchPreview.reduce((total, item) => total + (item.additions || diffStats(item.diff || '').additions), 0)} added</span>
                  <span>{patchPreview.reduce((total, item) => total + (item.deletions || diffStats(item.diff || '').deletions), 0)} removed</span>
                </div>
                <div className={styles.reviewFileList}>
                  {patchPreview.map((item) => {
                    const stats = diffStats(item.diff || '');
                    const active = selectedPatch?.file_id === item.file_id;
                    return (
                      <button
                        key={item.file_id}
                        className={active ? styles.reviewFileActive : styles.reviewFile}
                        type="button"
                        onClick={() => setSelectedPatchFileId(item.file_id)}
                      >
                        <span><FileCode2 size={14} /> {item.filename}</span>
                        <em>+{item.additions || stats.additions} / -{item.deletions || stats.deletions}</em>
                      </button>
                    );
                  })}
                </div>
                {selectedPatch && (
                  <div className={styles.reviewDetail}>
                    <div className={styles.reviewDetailHeader}>
                      <span>{selectedPatch.filename}</span>
                      <em>+{selectedPatch.additions || selectedStats.additions} / -{selectedPatch.deletions || selectedStats.deletions}</em>
                    </div>
                    <Diff diff={selectedPatch.diff} />
                    <div className={styles.changeActions}>
                      <button type="button" onClick={() => onApplyFile(selectedPatch.file_id)} disabled={!canApply}>
                        <Check size={14} /> Apply selected
                      </button>
                      <button type="button" onClick={() => onRejectFile(selectedPatch.file_id)} disabled={!hasPatch}>
                        <X size={14} /> Reject selected
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
            <div className={styles.tabActionStack}>
              <button className={styles.approveButton} type="button" onClick={onApply} disabled={!canApply}>
                <Check size={15} /> Approve all changes
              </button>
              <button className={styles.rejectButton} type="button" onClick={onReject} disabled={!hasPatch}>
                <X size={15} /> Reject changes
              </button>
            </div>
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
                <span>{snapshot.file_count || snapshot.files?.length || 0} file(s) {snapshot.applied_at ? `- ${new Date(snapshot.applied_at).toLocaleString()}` : ''}</span>
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
          <div className={styles.previewPanel}>
          <div className={styles.changesHeader}>
            <span>Preview</span>
            <strong>{previewChecks.length}</strong>
          </div>
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
          <div className={styles.previewButtonRow}>
            <button className={styles.commandButton} type="button" onClick={onStartPreview} disabled={!canStartPreview}>
              Start live
            </button>
            <button className={styles.commandButton} type="button" onClick={onStopPreview} disabled={!canStartPreview}>
              Stop
            </button>
          </div>
          <button className={styles.fullWidthButton} type="button" onClick={onLoadPreviewLogs} disabled={!canStartPreview}>
            Load preview logs
          </button>
          {previewChecks.length > 0 && (
            <div className={styles.previewEvidence}>
              {previewChecks.slice(-4).reverse().map((check, index) => (
                <div className={check.status === 'passed' ? styles.previewEvidencePass : styles.previewEvidenceFail} key={`${check.url}-${check.checked_at || index}`}>
                  <div>
                    <strong>{check.status || 'unknown'} {check.status_code ? `HTTP ${check.status_code}` : ''}</strong>
                    <span>{check.title || check.url}</span>
                  </div>
                  {check.issues?.length ? <em>{check.issues.join(', ')}</em> : <em>No issue markers</em>}
                </div>
              ))}
            </div>
          )}
          {previewLogs?.logs && (
            <div className={styles.previewLogs}>
              <div className={styles.meta}>
                {previewLogs.status || 'preview'} {previewLogs.issues?.length ? `- ${previewLogs.issues.join(', ')}` : ''}
              </div>
              {previewLogs.excerpts?.length ? (
                <div className={styles.previewExcerpts}>
                  {previewLogs.excerpts.map((line, index) => <span key={`${line}-${index}`}>{line}</span>)}
                </div>
              ) : null}
              <pre>{previewLogs.logs}</pre>
            </div>
          )}
          {previewUrl.trim() && (
            <iframe className={styles.previewFrame} src={previewUrl.trim()} title="Workspace preview" sandbox="allow-scripts allow-same-origin allow-forms" />
          )}
        </div>
        )}

        {activeTab === 'git' && (
          <div className={styles.previewPanel}>
          <div className={styles.changesHeader}>
            <span>GitHub App</span>
            <strong>{githubStatus?.connected ? 'connected' : githubStatus?.configured ? 'ready' : 'not configured'}</strong>
          </div>
          {githubStatus?.connected ? (
            <div className={styles.gitConnectionCard}>
              <strong>{githubStatus.account?.login || 'GitHub connected'}</strong>
              <span>{githubStatus.account?.type || 'installation'} · {githubRepositories.length} repo(s)</span>
            </div>
          ) : (
            <button className={styles.fullWidthButton} type="button" onClick={onConnectGithubApp}>
              Connect GitHub
            </button>
          )}
          <button className={styles.fullWidthButton} type="button" onClick={onRefreshGithub}>
            Refresh GitHub
          </button>
          <label className={styles.formLabel}>
            Choose repo
            <select className={styles.previewInput} value={selectedGithubRepo} onChange={(event) => onGithubRepoChange(event.target.value)} disabled={!githubStatus?.connected}>
              <option value="">Select repository</option>
              {githubRepositories.map((repo) => (
                <option key={repo.full_name} value={repo.full_name}>
                  {repo.full_name}{repo.private ? ' · private' : ''}
                </option>
              ))}
            </select>
          </label>
          <button className={styles.fullWidthButton} type="button" onClick={onImportRepo} disabled={!selectedGithubRepo || !canUseGit}>
            Import repo
          </button>
          <label className={styles.formLabel}>
            Working branch
            <input
              className={styles.previewInput}
              value={githubBranchName}
              onChange={(event) => onGithubBranchNameChange(event.target.value)}
              placeholder="nexus/workspace-update"
            />
          </label>
          <button className={styles.fullWidthButton} type="button" onClick={onCreateGithubBranch} disabled={!selectedGithubRepo || !canUseGit}>
            Create branch
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onPreparePr} disabled={!canUseGit}>
            Prepare PR
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onCommitGithubChanges} disabled={!canUseGit}>
            Commit approved changes
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onOpenPr} disabled={!canUseGit}>
            Open PR
          </button>
          <button className={styles.fullWidthButton} type="button" onClick={onCheckGithubPrStatus} disabled={!canUseGit}>
            View PR/check status
          </button>
          {githubStatus?.selected_repo && <div className={styles.contextMemory}>Repo: {githubStatus.selected_repo}</div>}
          {githubStatus?.working_branch && <div className={styles.contextMemory}>Branch: {githubStatus.working_branch}</div>}
          {githubStatus?.latest_commit_sha && <div className={styles.contextMemory}>Commit: {githubStatus.latest_commit_sha.slice(0, 12)}</div>}
          {githubStatus?.pull_request_url && (
            <a className={styles.contextMemory} href={githubStatus.pull_request_url} target="_blank" rel="noreferrer">Open pull request</a>
          )}
          {(githubStatus?.checks || []).slice(0, 5).map((check) => (
            <div className={styles.contextLine} key={`${check.name}-${check.html_url}`}>
              <strong>{check.name || 'check'}</strong>
              <span>{check.conclusion || check.status || 'queued'}</span>
            </div>
          ))}
          <details className={styles.advancedBox}>
            <summary>Advanced manual URL fallback</summary>
            <div className={styles.previewInputRow}>
              <input
                className={styles.previewInput}
                value={repoUrl}
                onChange={(event) => onRepoUrlChange(event.target.value)}
                placeholder="https://github.com/org/repo"
              />
              <button className={styles.commandButton} type="button" onClick={onConnectRepo} disabled={!repoUrl.trim() || !canUseGit}>
                Connect
              </button>
            </div>
          </details>
        </div>
        )}

        {activeTab === 'jobs' && (
          <div className={styles.jobStack}>
            <div className={styles.changesHeader}>
              <span>Durable Jobs</span>
              <strong>{jobs.length}</strong>
            </div>
            <button className={styles.fullWidthButton} type="button" onClick={onRefreshJobs}>
              Refresh jobs
            </button>
            {jobs.length === 0 && <div className={styles.meta}>No durable jobs yet.</div>}
            {jobs.slice(0, 8).map((job) => {
              const running = ['running', 'queued'].includes(job.status);
              const failed = ['failed', 'cancelled', 'timeout', 'blocked', 'interrupted'].includes(job.status);
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
                  <button className={styles.rejectButton} type="button" onClick={() => onCancelJob(job.id)}>
                    Cancel job
                  </button>
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
              Activity appears here as NEXUS reads files, researches, designs, edits, and prepares deployment steps.
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
