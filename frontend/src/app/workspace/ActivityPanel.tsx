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
  commands_run?: Array<{ command?: string; status?: string; return_code?: number | null } | string>;
  result?: Record<string, any>;
  created_at?: string;
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
  routes?: Array<{ filename: string; kind: string }>;
  components?: Array<{ filename: string; line: number; name: string }>;
  hotspots?: Array<{ filename: string; line: number; snippet: string }>;
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
  onRepoUrlChange,
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
            {(analysis.components || []).slice(0, 3).map((component) => (
              <div className={styles.contextMemory} key={`${component.filename}-${component.line}`}>Component: {component.name} in {component.filename}</div>
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
        )}

        {activeTab === 'jobs' && (
          <div className={styles.jobStack}>
            <div className={styles.meta}>Durable jobs</div>
            {jobs.length === 0 && <div className={styles.meta}>No durable jobs yet.</div>}
            {jobs.slice(0, 5).map((job) => (
              <details className={styles.jobDetail} key={job.id}>
                <summary>
                  <span>{job.mode}</span>
                  <strong>{job.status}</strong>
                </summary>
                {job.prompt && <p>{job.prompt}</p>}
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
                    Commands: {(job.commands_run || []).map((command) => typeof command === 'string' ? command : command.command).filter(Boolean).join(', ')}
                  </div>
                )}
              </details>
            ))}
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
