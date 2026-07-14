import type { ActivityEvent, PreviewCheck } from './ActivityPanel';
import type { WorkspaceMode } from './ConversationPanel';
import type { WorkspaceWorkReceipt } from './WorkReceipt';
import { normalizeWorkspaceSuggestion } from './workspaceSuggestions';

export const model = { llm_provider: 'nexus', llm_model: 'Arceus-Code' };
export const OPEN_PROJECTS_KEY = 'nexus.code.open_projects';
export const ACTIVE_PROJECT_KEY = 'nexus.code.active_project';
export const TERMINAL_PREFS_KEY = 'nexus.code.terminal_preferences';
export const MAX_OPEN_PROJECTS = 3;

export type CodeProject = {
  id: string;
  name: string;
  description?: string;
  repo_url?: string;
  status?: string;
  file_ids?: string[];
  file_count?: number;
  metadata?: Record<string, any>;
  local_workspace_path?: string;
  openable?: boolean;
  active_session_id?: string | null;
  last_opened_at?: string | null;
};

export type PendingProjectOpen = { kind: 'project'; projectId: string } | { kind: 'local'; localPath: string } | null;

export type WorkspaceRightPanelView = 'explorer' | 'org' | 'changes' | 'jobs' | 'preview' | 'git' | 'apps' | 'tasks';

export type WorkspaceCommandAction = {
  id: string;
  title: string;
  detail: string;
  keywords: string;
  rank: number;
  run: () => void | Promise<void>;
};

export function id(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function inferModes(prompt: string, selected: WorkspaceMode): WorkspaceMode[] {
  if (selected !== 'auto') return [selected];
  const text = prompt.toLowerCase();
  const modes: WorkspaceMode[] = [];
  if (/(research|latest|best practice|compare|search|find)/.test(text)) modes.push('research');
  if (/(design|ui|ux|screen|layout|component|page)/.test(text)) modes.push('design');
  if (/(deploy|railway|vercel|render|production|release)/.test(text)) modes.push('deploy');
  if (/(code|build|fix|bug|api|endpoint|implement|refactor|test)/.test(text)) modes.push('code');
  return modes.length ? modes : ['code'];
}

export function inferReceiptIntent(prompt: string) {
  const text = prompt.toLowerCase();
  if (/(fix|bug|error|broken|not working|issue)/.test(text)) return 'Fix';
  if (/(design|ui|ux|layout|screen|component|style)/.test(text)) return 'Design';
  if (/(deploy|railway|vercel|production|release)/.test(text)) return 'Deploy';
  if (/(test|lint|typecheck|build|compile)/.test(text)) return 'Check';
  if (/(research|compare|latest|find|search)/.test(text)) return 'Research';
  return 'Build';
}

export function summarizePatch(raw: string) {
  try {
    const payload = JSON.parse(raw);
    const files = Array.isArray(payload.files) ? payload.files : [];
    return files.map((file: any) => `✏️ ${file.filename || file.file_id || 'file'}\nFull replacement prepared.`).join('\n\n') || raw;
  } catch {
    return raw;
  }
}

export function summarizePreview(preview: Array<{ filename: string; additions?: number; deletions?: number }>) {
  if (!preview.length) return 'Patch prepared for review.';
  return preview
    .map((file) => `Edited ${file.filename}: +${file.additions || 0} / -${file.deletions || 0}`)
    .join('\n');
}

export function buildPreviewReceipt(check: PreviewCheck, project?: string): WorkspaceWorkReceipt {
  const consoleCount = check.console_errors?.length || 0;
  const pageCount = check.page_errors?.length || 0;
  const networkCount = check.network_failures?.length || 0;
  const failed = check.status !== 'passed';
  const issues = [
    ...(check.issues || []),
    check.blank_page ? 'Blank page detected' : '',
    check.playwright_error ? `Browser check error: ${check.playwright_error}` : '',
  ].filter(Boolean);
  const evidence = [
    check.screenshot_base64 || check.screenshot_url ? 'Screenshot captured' : 'No screenshot captured',
    `${consoleCount} console error${consoleCount === 1 ? '' : 's'}`,
    `${pageCount} page error${pageCount === 1 ? '' : 's'}`,
    `${networkCount} network failure${networkCount === 1 ? '' : 's'}`,
    check.first_contentful_paint_ms ? `FCP ${Math.round(check.first_contentful_paint_ms)}ms` : '',
  ].filter(Boolean).join(' · ');

  return {
    summary: failed ? 'Preview verification found an issue.' : 'Preview verification passed.',
    mode: 'deploy',
    intent: 'Verify',
    project,
    plan: [
      `URL: ${check.url}`,
      check.status_code ? `HTTP: ${check.status_code}` : '',
      check.title ? `Title: ${check.title}` : '',
      evidence,
      issues.length ? `Issues: ${issues.join(', ')}` : 'No browser, console, network, or blank-page issue detected.',
    ].filter(Boolean).join('\n'),
    checks: [
      { label: 'Browser preview', status: check.status },
      { label: 'Screenshot', status: check.screenshot_base64 || check.screenshot_url ? 'captured' : 'missing' },
      { label: 'Console errors', status: consoleCount ? `${consoleCount} failed` : 'passed' },
      { label: 'Network requests', status: networkCount ? `${networkCount} failed` : 'passed' },
      { label: 'Blank-page detection', status: check.blank_page ? 'failed' : 'passed' },
    ],
    checksPassed: failed ? 0 : 1,
    checksFailed: failed ? 1 : 0,
    approvalState: failed ? 'needs fix' : 'verified',
    nextActions: failed ? [
      normalizeWorkspaceSuggestion({
        id: 'fix-preview-issue',
        title: 'Fix preview issue',
        summary: 'Use screenshot, console, and network evidence to prepare the smallest safe patch.',
        prompt: check.fix_suggestion_prompt || `Fix the latest preview issue for ${check.url}. Use the captured browser evidence and avoid unrelated changes.`,
        mode: 'code',
        risk: 'medium',
        requires_approval: true,
      }),
      normalizeWorkspaceSuggestion({
        id: 'open-preview-evidence',
        title: 'Inspect preview evidence',
        summary: 'Open the Preview drawer and compare screenshot, console errors, and network failures.',
        prompt: 'Summarize the latest preview evidence and identify the most likely source file to inspect next.',
        mode: 'plan',
        risk: 'low',
      }),
      normalizeWorkspaceSuggestion({
        id: 'run-local-checks-after-preview',
        title: 'Run checks after fix',
        summary: 'Run the detected build, lint, or test command after the preview fix is reviewed.',
        prompt: 'Run the safest available project checks and summarize failures with exact commands and files.',
        mode: 'code',
        risk: 'low',
      }),
    ] : [
      normalizeWorkspaceSuggestion({
        id: 'prepare-github-pr',
        title: 'Prepare PR',
        summary: 'Turn approved changes and verified preview evidence into a pull request summary.',
        prompt: 'Prepare a concise PR title and body from the latest work receipt and preview verification.',
        mode: 'deploy',
        risk: 'low',
      }),
      normalizeWorkspaceSuggestion({
        id: 'run-regression-checks',
        title: 'Run regression checks',
        summary: 'Run build, lint, and test commands before committing the work.',
        prompt: 'Run the detected build, lint, and test commands and report pass/fail evidence.',
        mode: 'code',
        risk: 'low',
      }),
      normalizeWorkspaceSuggestion({
        id: 'document-next-step',
        title: 'Choose next task',
        summary: 'Use Arceus next-action guidance to decide what should happen after the verified preview.',
        prompt: 'Suggest the next 3 project actions using current files, preview status, jobs, and pending changes.',
        mode: 'plan',
        risk: 'low',
      }),
    ],
  };
}

export function buildWorkReceiptFromPayload(payload: any, fallback: WorkspaceWorkReceipt): WorkspaceWorkReceipt {
  const receipt = payload?.work_receipt || payload?.workReceipt;
  if (!receipt || typeof receipt !== 'object') return fallback;
  return {
    ...fallback,
    summary: receipt.summary || fallback.summary,
    mode: receipt.mode || fallback.mode,
    intent: receipt.intent || fallback.intent,
    project: receipt.project || fallback.project,
    session: receipt.session || fallback.session,
    plan: receipt.plan || fallback.plan,
    filesInspected: receipt.files_inspected || receipt.filesInspected || fallback.filesInspected,
    filesChanged: receipt.files_changed || receipt.filesChanged || fallback.filesChanged,
    foldersCreated: receipt.folders_created || receipt.foldersCreated || fallback.foldersCreated,
    commands: receipt.commands_run || receipt.commands || fallback.commands,
    checks: receipt.checks || fallback.checks,
    checksPassed: receipt.checks_passed ?? receipt.checksPassed ?? fallback.checksPassed,
    checksFailed: receipt.checks_failed ?? receipt.checksFailed ?? fallback.checksFailed,
    approvalState: receipt.approval_state || receipt.approvalState || fallback.approvalState,
    lineImpact: receipt.line_impact || receipt.lineImpact || fallback.lineImpact,
    nextActions: receipt.next_actions || receipt.nextActions || fallback.nextActions,
    rollbackAvailable: receipt.rollback_available ?? receipt.rollbackAvailable ?? fallback.rollbackAvailable,
  };
}

export function promptTargetsActiveFile(value: string) {
  return /\b(this file|current file|active file|the file|opened file|selected file|analyze the file|analyse the file|explain this|explain the file|review this|fix this|refactor this|test this|debug this)\b/i.test(value);
}

export function normalizeEvents(events: any[]): ActivityEvent[] {
  return [...(events || [])].reverse().map((event, index) => ({
    id: event.id || `stored-${index}`,
    kind: event.kind || 'start',
    message: event.message || 'Workspace activity',
    detail: event.detail,
    diff: event.diff,
  }));
}
