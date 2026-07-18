'use client';

import { AlertTriangle, CheckCircle2, Code2, FileCode2, ListChecks, RotateCcw, Terminal } from 'lucide-react';
import styles from './Workspace.module.css';
import type { WorkspaceSuggestion } from './workspaceSuggestions';
import type { WorkspaceMode } from './ConversationPanel';
import type { ErrorClass } from './errorClassifier';

export type WorkspaceWorkReceipt = {
  summary: string;
  mode: WorkspaceMode | 'mixed' | 'error';
  intent: string;
  project?: string;
  session?: string;
  plan?: string;
  filesInspected?: string[];
  filesChanged?: Array<{ filename: string; operation?: string; additions?: number; deletions?: number }>;
  foldersCreated?: string[];
  commands?: Array<{ label?: string; command?: string; status?: string; duration_ms?: number }>;
  checks?: Array<{ label?: string; name?: string; status?: string }>;
  checksPassed?: number;
  checksFailed?: number;
  approvalState?: string;
  lineImpact?: { additions?: number; deletions?: number };
  nextActions?: WorkspaceSuggestion[];
  rollbackAvailable?: boolean;
  errorClass?: ErrorClass | string;
  errorHint?: string;
  rawError?: string;
};

function compactText(value: string, max = 180) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1).trim()}...`;
}

type Props = {
  receipt: WorkspaceWorkReceipt;
  onTypeSuggestion: (suggestion: WorkspaceSuggestion) => void;
  onOpenTool?: (tool: 'terminal' | 'changes' | 'jobs' | 'preview') => void;
  onOpenFile?: (filename: string) => void | Promise<void>;
  onRollback?: () => void | Promise<void>;
  busy: boolean;
};

function statusTone(receipt: WorkspaceWorkReceipt) {
  const approval = (receipt.approvalState || '').toLowerCase();
  const commandFailed = (receipt.commands || []).some((command) => /fail|error|timeout|blocked/i.test(command.status || ''));
  const checkFailed = (receipt.checks || []).some((check) => /fail|error|timeout|blocked/i.test(check.status || ''));
  if (receipt.mode === 'error' || commandFailed || checkFailed || (receipt.checksFailed || 0) > 0 || /fail|error|blocked|timeout/.test(approval)) return 'failed';
  if (/pending|waiting|review/.test(approval)) return 'pending';
  if ((receipt.filesChanged?.length || 0) > 0 || (receipt.checks?.length || 0) > 0 || /done|approved|restored/.test(approval)) return 'passed';
  return 'neutral';
}

function receiptTitle(receipt: WorkspaceWorkReceipt, additions: number, deletions: number) {
  const changed = receipt.filesChanged?.length || 0;
  if (changed > 0) return `${changed} file${changed === 1 ? '' : 's'} changed  +${additions} / -${deletions} lines`;
  return receipt.summary;
}

function errorActionLabel(errorClass?: string) {
  if (errorClass === 'quota_exceeded') return 'Upgrade Plan';
  if (errorClass === 'api_offline') return 'Check Services';
  if (errorClass === 'patch_conflict') return 'Reset Patch';
  if (errorClass === 'model_error') return 'Check API Key';
  if (errorClass === 'file_too_large') return 'Open Files';
  if (errorClass === 'command_failed') return 'Open Terminal';
  return 'View Details';
}

export default function WorkReceipt({ receipt, onTypeSuggestion, onOpenTool, onOpenFile, onRollback, busy }: Props) {
  const lineImpact = receipt.lineImpact || (receipt.filesChanged || []).reduce(
    (stats, file) => ({
      additions: stats.additions + (file.additions || 0),
      deletions: stats.deletions + (file.deletions || 0),
    }),
    { additions: 0, deletions: 0 }
  );
  const tone = statusTone(receipt);
  const rollbackAvailable = Boolean(receipt.rollbackAvailable || (onRollback && receipt.filesChanged?.length && /approved|done|restored|applied/i.test(receipt.approvalState || '')));

  return (
    <div className={styles.workReceipt} data-status={tone}>
      {receipt.errorClass && (
        <div className={styles.workReceiptError} data-error-class={receipt.errorClass}>
          <AlertTriangle size={13} />
          <div>
            <strong>{receipt.summary}</strong>
            <span>{receipt.errorHint || 'Review the details and try again.'}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              if (receipt.errorClass === 'command_failed' || receipt.errorClass === 'api_offline') onOpenTool?.('terminal');
              else if (receipt.errorClass === 'patch_conflict') onOpenTool?.('changes');
              else onOpenTool?.('jobs');
            }}
          >
            {errorActionLabel(receipt.errorClass)}
          </button>
        </div>
      )}
      <div className={styles.workReceiptSummary}>
        <strong>{receiptTitle(receipt, lineImpact.additions || 0, lineImpact.deletions || 0)}</strong>
        <div>
          <span>{receipt.intent}</span>
          <span>{receipt.mode}</span>
          {receipt.project && <span>{receipt.project}</span>}
          {receipt.approvalState && <span>{receipt.approvalState}</span>}
        </div>
      </div>
      <div className={styles.receiptMetricGrid}>
        <span><FileCode2 size={12} /> {receipt.filesInspected?.length || 0} inspected</span>
        <span><Code2 size={12} /> {receipt.filesChanged?.length || 0} changed</span>
        <span><Terminal size={12} /> {receipt.commands?.length || 0} commands</span>
        <span><CheckCircle2 size={12} /> +{lineImpact.additions || 0} / -{lineImpact.deletions || 0}</span>
        <span><ListChecks size={12} /> {receipt.checksPassed || 0} passed / {receipt.checksFailed || 0} failed</span>
      </div>
      {onOpenTool && (
        <div className={styles.receiptToolRow}>
          {!!receipt.filesChanged?.length && <button type="button" onClick={() => onOpenTool('changes')}>Review changes</button>}
          {!!receipt.commands?.length && <button type="button" onClick={() => onOpenTool('terminal')}>Open terminal</button>}
          {!!receipt.checks?.length && <button type="button" onClick={() => onOpenTool('jobs')}>View checks</button>}
          <button type="button" onClick={() => onOpenTool('preview')}>Preview</button>
          {rollbackAvailable && onRollback && (
            <button type="button" className={styles.receiptRollbackButton} onClick={() => onRollback()} disabled={busy}>
              <RotateCcw size={12} />
              Undo changes
            </button>
          )}
        </div>
      )}
      {receipt.plan && (
        <details className={styles.receiptSection} open>
          <summary>Plan</summary>
          <p>{compactText(receipt.plan, 420)}</p>
        </details>
      )}
      {!!receipt.filesChanged?.length && (
        <details className={styles.receiptSection} open>
          <summary>Changes</summary>
          <div className={styles.receiptRows}>
            {receipt.filesChanged.slice(0, 8).map((file) => (
              <button
                type="button"
                className={styles.receiptFileButton}
                key={`${file.filename}-${file.operation || 'change'}`}
                onClick={() => onOpenFile?.(file.filename)}
                disabled={!onOpenFile}
              >
                <FileCode2 size={12} />
                <strong>{file.operation || 'modify'}</strong>
                <em>{file.filename}</em>
                <small>+{file.additions || 0} / -{file.deletions || 0}</small>
              </button>
            ))}
          </div>
        </details>
      )}
      {!!receipt.filesInspected?.length && (
        <details className={styles.receiptSection}>
          <summary>Files inspected</summary>
          <div className={styles.receiptPills}>
            {receipt.filesInspected.slice(0, 10).map((file) => (
              <button
                type="button"
                className={styles.receiptPillButton}
                key={file}
                onClick={() => onOpenFile?.(file)}
                disabled={!onOpenFile}
              >
                {file}
              </button>
            ))}
          </div>
        </details>
      )}
      {!!receipt.commands?.length && (
        <details className={styles.receiptSection}>
          <summary>Commands</summary>
          <div className={styles.receiptRows}>
            {receipt.commands.slice(0, 6).map((command) => (
              <span key={`${command.label || command.command}-${command.status || 'recommended'}`}>
                <Terminal size={12} />
                <em>{command.label || command.command}</em>
                <small>{command.status || 'recommended'}{command.duration_ms ? ` · ${(command.duration_ms / 1000).toFixed(1)}s` : ''}</small>
              </span>
            ))}
          </div>
        </details>
      )}
      {!!receipt.checks?.length && (
        <details className={styles.receiptSection}>
          <summary>Checks</summary>
          <div className={styles.receiptRows}>
            {receipt.checks.slice(0, 6).map((check) => (
              <span key={`${check.label || check.name}-${check.status || 'pending'}`}>
                <ListChecks size={12} />
                <em>{check.label || check.name}</em>
                <small>{check.status || 'recommended'}</small>
              </span>
            ))}
          </div>
        </details>
      )}
      {!!receipt.nextActions?.length && (
        <details className={styles.receiptSection} open>
          <summary>Next</summary>
          <div className={styles.receiptNextActions}>
            {receipt.nextActions.slice(0, 3).map((action) => (
              <article key={action.id}>
                <div>
                  <strong>{action.title}</strong>
                  <span>{action.summary}</span>
                </div>
                <button type="button" onClick={() => onTypeSuggestion(action)} disabled={busy}>Type</button>
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
