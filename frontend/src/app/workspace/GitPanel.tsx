'use client';

import { CheckCircle2, ClipboardList, GitBranch, GitPullRequest, Lock, RefreshCw, Rocket, XCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import styles from './Workspace.module.css';
import type { GitHubBranch, GitHubRepository, GitHubStatus, PatchPreviewItem } from './ActivityPanel';

export type GitDeliveryPackage = {
  title?: string;
  commit_message?: string;
  body?: string;
  release_notes?: string;
  ready?: boolean;
  created_at?: string;
  risk_summary?: string[];
  checklist?: Array<{ label?: string; done?: boolean }>;
  impact?: {
    files_changed?: number;
    additions?: number;
    deletions?: number;
    commands?: number;
    checks?: number;
  };
};

type Props = {
  githubStatus: GitHubStatus | null;
  githubRepositories: GitHubRepository[];
  githubBranches?: GitHubBranch[];
  selectedGithubRepo: string;
  githubBaseBranch: string;
  githubBranchName: string;
  patchPreview: PatchPreviewItem[];
  deliveryPackage?: GitDeliveryPackage | null;
  canUseGit: boolean;
  busy: boolean;
  onGithubRepoChange: (value: string) => void;
  onGithubBaseBranchChange: (value: string) => void;
  onGithubBranchNameChange: (value: string) => void;
  onConnectGithubApp: () => void;
  onRefreshGithub: () => void;
  onImportRepo: () => void;
  onCreateGithubBranch: () => void;
  onCommitGithubChanges: (message?: string, filenames?: string[]) => void;
  onOpenPr: (title?: string, body?: string) => void;
  onCommitAndOpenPr: (payload: { commit_message?: string; title?: string; body?: string; branch_name?: string; filenames?: string[] }) => void;
  onCheckGithubPrStatus: () => void;
};

function checkState(check: { status?: string; conclusion?: string }) {
  if (check.conclusion === 'success') return 'passed';
  if (['failure', 'cancelled', 'timed_out', 'action_required'].includes(check.conclusion || '')) return 'failed';
  return check.status || 'queued';
}

export default function GitPanel({
  githubStatus,
  githubRepositories,
  githubBranches = [],
  selectedGithubRepo,
  githubBaseBranch,
  githubBranchName,
  patchPreview,
  deliveryPackage,
  canUseGit,
  busy,
  onGithubRepoChange,
  onGithubBaseBranchChange,
  onGithubBranchNameChange,
  onConnectGithubApp,
  onRefreshGithub,
  onImportRepo,
  onCreateGithubBranch,
  onCommitGithubChanges,
  onOpenPr,
  onCommitAndOpenPr,
  onCheckGithubPrStatus,
}: Props) {
  const [commitMessage, setCommitMessage] = useState('Arceus Code workspace changes');
  const [prTitle, setPrTitle] = useState('Arceus Code workspace changes');
  const [prBody, setPrBody] = useState('');
  const [selectedStageFiles, setSelectedStageFiles] = useState<string[]>([]);
  const [repoSearch, setRepoSearch] = useState('');
  const [connectPolling, setConnectPolling] = useState(false);
  const [checkPollUrl, setCheckPollUrl] = useState('');
  const refreshGithubRef = useRef(onRefreshGithub);
  const checkStatusRef = useRef(onCheckGithubPrStatus);

  const staged = useMemo(() => {
    const approved = githubStatus?.staged?.staged || [];
    if (approved.length) {
      return approved.map((item) => ({
        filename: item.filename || '',
        operation: item.operation || 'modify',
        additions: item.additions || 0,
        deletions: item.deletions || 0,
      })).filter((item) => item.filename);
    }
    return patchPreview.map((item) => ({
      filename: item.new_filename || item.filename,
      operation: item.operation || 'modify',
      additions: item.additions || 0,
      deletions: item.deletions || 0,
    }));
  }, [githubStatus?.staged?.staged, patchPreview]);
  const usingAppliedStagedFiles = Boolean(githubStatus?.staged?.staged?.length);

  const stagedFilenames = useMemo(() => staged.map((file) => file.filename).filter(Boolean), [staged]);
  const effectiveStageFiles = selectedStageFiles.filter((filename) => stagedFilenames.includes(filename));
  const commitFilenames = effectiveStageFiles.length ? effectiveStageFiles : stagedFilenames;
  const currentRepo = githubRepositories.find((repo) => repo.full_name === selectedGithubRepo);
  const filteredRepositories = useMemo(() => {
    const query = repoSearch.trim().toLowerCase();
    if (!query) return githubRepositories;
    return githubRepositories.filter((repo) => repo.full_name.toLowerCase().includes(query));
  }, [githubRepositories, repoSearch]);
  const invalidBranch = Boolean(githubBranchName && /[^\w./-]/.test(githubBranchName));

  const connected = Boolean(githubStatus?.connected);
  const checks = githubStatus?.checks || [];
  const checkSummary = githubStatus?.check_summary;
  const hasRunningChecks = checks.some((check) => ['queued', 'in_progress', 'requested'].includes(check.status || ''));
  const defaultCommitMessage = 'Arceus Code workspace changes';
  const defaultPrTitle = 'Arceus Code workspace changes';

  useEffect(() => {
    refreshGithubRef.current = onRefreshGithub;
  }, [onRefreshGithub]);

  useEffect(() => {
    checkStatusRef.current = onCheckGithubPrStatus;
  }, [onCheckGithubPrStatus]);

  useEffect(() => {
    if (!connectPolling || connected) {
      if (connected) setConnectPolling(false);
      return;
    }
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      refreshGithubRef.current();
      if (attempts >= 15) {
        setConnectPolling(false);
        window.clearInterval(timer);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [connectPolling, connected]);

  useEffect(() => {
    if (githubStatus?.pull_request_url && githubStatus.pull_request_url !== checkPollUrl) {
      setCheckPollUrl(githubStatus.pull_request_url);
    }
  }, [githubStatus?.pull_request_url, checkPollUrl]);

  useEffect(() => {
    if (!checkPollUrl) return;
    if (checks.length > 0 && !hasRunningChecks) {
      setCheckPollUrl('');
      return;
    }
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      checkStatusRef.current();
      if (attempts >= 30) {
        setCheckPollUrl('');
        window.clearInterval(timer);
      }
    }, 10000);
    return () => window.clearInterval(timer);
  }, [checkPollUrl, checks.length, hasRunningChecks]);

  const applyDeliveryPackage = (force = false) => {
    if (!deliveryPackage) return;
    const nextCommitMessage = deliveryPackage.commit_message || deliveryPackage.title || defaultCommitMessage;
    const nextPrTitle = deliveryPackage.title || nextCommitMessage || defaultPrTitle;
    const nextPrBody = deliveryPackage.body || deliveryPackage.release_notes || '';
    setCommitMessage((current) => (force || !current.trim() || current === defaultCommitMessage ? nextCommitMessage : current));
    setPrTitle((current) => (force || !current.trim() || current === defaultPrTitle ? nextPrTitle : current));
    setPrBody((current) => (force || !current.trim() ? nextPrBody : current));
  };

  useEffect(() => {
    applyDeliveryPackage(false);
  }, [deliveryPackage?.created_at, deliveryPackage?.title, deliveryPackage?.commit_message, deliveryPackage?.body]);

  const handleConnect = () => {
    onConnectGithubApp();
    setConnectPolling(true);
  };

  return (
    <div className={styles.gitPanelShell}>
      <div className={styles.gitHero}>
        <div>
          <span><GitPullRequest size={13} /> GitHub App</span>
          <strong>{connected ? 'connected' : githubStatus?.configured ? 'ready' : 'not configured'}</strong>
        </div>
        <em>{githubStatus?.account?.login || 'Install Arceus GitHub App to import and open PRs.'}</em>
      </div>

      <div className={styles.previewButtonRow}>
        <button className={styles.commandButton} type="button" onClick={handleConnect} disabled={busy || connectPolling}>
          <GitPullRequest size={13} /> {connectPolling ? 'Waiting...' : connected ? 'Reconnect' : 'Connect'}
        </button>
        <button className={styles.commandButton} type="button" onClick={onRefreshGithub} disabled={busy}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {deliveryPackage && (
        <div className={styles.gitDeliveryPackage}>
          <div>
            <span><ClipboardList size={13} /> Engineering Org package</span>
            <strong data-ready={deliveryPackage.ready ? 'true' : 'false'}>{deliveryPackage.ready ? 'ready' : 'needs review'}</strong>
          </div>
          <p>{deliveryPackage.title || 'Prepared delivery package'}</p>
          <div className={styles.gitDeliveryImpact}>
            <small>{deliveryPackage.impact?.files_changed || 0} files</small>
            <small>+{deliveryPackage.impact?.additions || 0} / -{deliveryPackage.impact?.deletions || 0}</small>
            <small>{deliveryPackage.impact?.commands || 0} commands</small>
            <small>{deliveryPackage.impact?.checks || 0} checks</small>
          </div>
          {Boolean(deliveryPackage.checklist?.length) && (
            <div className={styles.gitDeliveryChecklist}>
              {deliveryPackage.checklist?.slice(0, 4).map((item, index) => (
                <small key={`${item.label || 'check'}-${index}`} data-done={item.done ? 'true' : 'false'}>
                  {item.done ? '✓' : '•'} {item.label || 'Review item'}
                </small>
              ))}
            </div>
          )}
          <button className={styles.fullWidthButton} type="button" onClick={() => applyDeliveryPackage(true)} disabled={busy}>
            Use package for commit and PR
          </button>
        </div>
      )}

      <label className={styles.gitField}>
        <span>Find repository</span>
        <input
          className={styles.previewInput}
          value={repoSearch}
          onChange={(event) => setRepoSearch(event.target.value)}
          placeholder="Search installation repositories..."
          disabled={!connected || busy}
        />
      </label>

      <label className={styles.gitField}>
        <span>Repository</span>
        <select className={styles.previewInput} value={selectedGithubRepo} onChange={(event) => onGithubRepoChange(event.target.value)} disabled={!connected || busy}>
          <option value="">Choose repository</option>
          {filteredRepositories.map((repo) => (
            <option key={repo.full_name} value={repo.full_name}>{repo.full_name}{repo.private ? ' · private' : ''}</option>
          ))}
        </select>
      </label>
      {currentRepo && (
        <div className={styles.gitRepoMeta}>
          <span>{currentRepo.full_name}</span>
          {currentRepo.private && <em><Lock size={11} /> private</em>}
          <strong>{currentRepo.default_branch || 'main'}</strong>
        </div>
      )}

      <div className={styles.previewButtonRow}>
        <button className={styles.fullWidthButton} type="button" onClick={onImportRepo} disabled={!selectedGithubRepo || !canUseGit}>
          Import repo
        </button>
      </div>

      <label className={styles.gitField}>
        <span>Base branch</span>
        <select
          className={styles.previewInput}
          value={githubBaseBranch || currentRepo?.default_branch || githubBranches[0]?.name || ''}
          disabled={!githubBranches.length || busy}
          onChange={(event) => {
            const value = event.target.value;
            onGithubBaseBranchChange(value);
            if (!githubBranchName) onGithubBranchNameChange(`arceus/${value.replace(/[^a-zA-Z0-9._-]/g, '-').toLowerCase()}`);
          }}
        >
          {githubBranches.length ? githubBranches.map((branch) => (
            <option key={branch.name} value={branch.name}>
              {branch.name}{branch.protected ? ' · protected' : ''}
            </option>
          )) : (
            <option value={currentRepo?.default_branch || ''}>{currentRepo?.default_branch || 'Import or refresh repo branches'}</option>
          )}
        </select>
      </label>

      <label className={styles.gitField}>
        <span>Working branch</span>
        <input
          className={styles.previewInput}
          value={githubBranchName}
          onChange={(event) => onGithubBranchNameChange(event.target.value)}
          placeholder="arceus/feature-name"
          aria-invalid={invalidBranch}
        />
      </label>
      {invalidBranch && <div className={styles.gitInlineError}>Branch names can use letters, numbers, underscore, dash, slash, and dot.</div>}
      <button className={styles.fullWidthButton} type="button" onClick={onCreateGithubBranch} disabled={!selectedGithubRepo || !canUseGit || invalidBranch}>
        <GitBranch size={13} /> Create branch
      </button>

      <div className={styles.gitStageBox}>
        <div className={styles.previewSectionTitle}>
          <span>{usingAppliedStagedFiles ? 'Approved files ready to commit' : 'Pending review files'}</span>
          <em>{staged.length}</em>
        </div>
        {staged.length ? staged.slice(0, 12).map((file) => {
          const checked = !effectiveStageFiles.length || effectiveStageFiles.includes(file.filename);
          return (
          <div className={styles.gitStageRow} key={`${file.operation}-${file.filename}`}>
            <label>
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => {
                  setSelectedStageFiles((current) => {
                    const normalized = current.length ? current.filter((name) => stagedFilenames.includes(name)) : stagedFilenames;
                    if (event.target.checked) return Array.from(new Set([...normalized, file.filename]));
                    const next = normalized.filter((name) => name !== file.filename);
                    return next.length === stagedFilenames.length ? [] : next;
                  });
                }}
              />
              <span>
                <strong>{file.filename}</strong>
                <em>{file.operation} · +{file.additions} / -{file.deletions}</em>
              </span>
            </label>
          </div>
        );}) : (
          <div className={styles.previewEmptySmall}>Apply reviewed changes before committing.</div>
        )}
      </div>

      <label className={styles.gitField}>
        <span>Commit message</span>
        <input className={styles.previewInput} value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} />
      </label>
      <button className={styles.fullWidthButton} type="button" onClick={() => onCommitGithubChanges(commitMessage, commitFilenames)} disabled={!canUseGit || !commitFilenames.length}>
        Commit selected changes
      </button>

      <label className={styles.gitField}>
        <span>PR title</span>
        <input className={styles.previewInput} value={prTitle} onChange={(event) => setPrTitle(event.target.value)} />
      </label>
      <label className={styles.gitField}>
        <span>PR body</span>
        <textarea className={styles.gitTextarea} value={prBody} onChange={(event) => setPrBody(event.target.value)} placeholder="Optional context. Arceus adds a work receipt automatically." />
      </label>

      <div className={styles.previewButtonRow}>
        <button className={styles.commandButton} type="button" onClick={() => onOpenPr(prTitle, prBody)} disabled={!canUseGit}>
          <GitPullRequest size={13} /> Open PR
        </button>
        <button
          className={styles.fullWidthButton}
          type="button"
          onClick={() => onCommitAndOpenPr({ commit_message: commitMessage, title: prTitle, body: prBody, branch_name: githubBranchName, filenames: commitFilenames })}
          disabled={!canUseGit || !commitFilenames.length || invalidBranch}
        >
          <Rocket size={13} /> Commit → PR
        </button>
      </div>

      <button className={styles.fullWidthButton} type="button" onClick={onCheckGithubPrStatus} disabled={!canUseGit}>
        Refresh PR checks
      </button>

      {githubStatus?.selected_repo && <div className={styles.contextMemory}>Repo: {githubStatus.selected_repo}</div>}
      {githubStatus?.working_branch && <div className={styles.contextMemory}>Branch: {githubStatus.working_branch}</div>}
      {githubStatus?.latest_commit_sha && <div className={styles.contextMemory}>Commit: {githubStatus.latest_commit_sha.slice(0, 12)}</div>}
      {githubStatus?.pull_request_url && (
        <a className={styles.gitPrLink} href={githubStatus.pull_request_url} target="_blank" rel="noreferrer">↗ View PR on GitHub</a>
      )}
      {checkSummary && (
        <div className={styles.gitCheckSummary}>
          <span>{checkSummary.total || 0} checks</span>
          <em>{checkSummary.passed || 0} passed</em>
          <em>{checkSummary.failed || 0} failed</em>
          <em>{checkSummary.running || 0} running</em>
        </div>
      )}

      {checks.length > 0 && (
        <div className={styles.gitChecks}>
          {checks.slice(0, 8).map((check) => {
            const state = checkState(check);
            return (
              <a className={styles.gitCheckRow} data-state={state} href={check.html_url || '#'} target="_blank" rel="noreferrer" key={`${check.name}-${check.html_url}`}>
                {state === 'passed' ? <CheckCircle2 size={13} /> : state === 'failed' ? <XCircle size={13} /> : <RefreshCw size={13} />}
                <span>{check.name || 'check'}</span>
                <em>{check.conclusion || check.status || 'queued'}</em>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
