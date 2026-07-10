import type { WorkspaceMode } from './ConversationPanel';

export type WorkspaceSuggestion = {
  id: string;
  title: string;
  summary: string;
  prompt: string;
  mode: WorkspaceMode;
  impact: string;
  fileHint: string;
  checkHint: string;
};

function compact(value: string, max = 160) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  return normalized.length > max ? `${normalized.slice(0, max - 1).trim()}...` : normalized;
}

function inferMode(prompt: string, selected: WorkspaceMode): WorkspaceMode {
  if (selected !== 'auto') return selected;
  const text = prompt.toLowerCase();
  if (/(design|ui|ux|layout|screen|component|visual|style)/.test(text)) return 'design';
  if (/(deploy|railway|vercel|render|production|release|domain)/.test(text)) return 'deploy';
  if (/(research|compare|latest|find|search|best)/.test(text)) return 'research';
  if (/(plan|roadmap|architecture|steps|think)/.test(text)) return 'plan';
  return 'code';
}

function subject(prompt: string) {
  return compact(prompt, 140) || 'the current workspace task';
}

export function buildWorkspaceSuggestions(
  prompt: string,
  mode: WorkspaceMode,
  selectedFileCount: number
): WorkspaceSuggestion[] {
  if (!prompt.trim()) return [];
  const task = subject(prompt);
  const inferred = inferMode(prompt, mode);
  const contextText = selectedFileCount > 0
    ? `${selectedFileCount} selected file${selectedFileCount === 1 ? '' : 's'}`
    : 'workspace files after inspection';

  const implementMode: WorkspaceMode = inferred === 'design' || inferred === 'deploy' || inferred === 'research' ? inferred : 'code';

  return [
    {
      id: 'plan-first',
      title: 'Plan the work first',
      summary: 'Turn the description into a short execution plan with impacted files, risks, and checks before editing.',
      mode: 'plan',
      impact: 'No code changes. Best when the request is broad or unclear.',
      fileHint: `Inspect ${contextText}; list likely files by name only.`,
      checkHint: 'Suggest build/test/lint commands, but do not run them yet.',
      prompt: `Create a concise implementation plan for: ${task}\n\nReturn only:\n1. Goal in one sentence\n2. Likely files/folders to inspect by name\n3. Three tasks in execution order\n4. Risks or questions\n5. Checks to run\n\nDo not edit files yet.`,
    },
    {
      id: 'safe-implement',
      title: 'Implement as reviewed patch',
      summary: 'Inspect relevant files, make the smallest useful change, then show files created/modified and line counts.',
      mode: implementMode,
      impact: 'Creates a reviewable patch. User approval is still required before applying.',
      fileHint: `Use ${contextText}; avoid touching unrelated files.`,
      checkHint: 'Prepare recommended checks and run only safe allowed commands.',
      prompt: `Implement this request as a small reviewed patch: ${task}\n\nBefore changing anything, infer the impacted files. Then create the minimal patch.\n\nIn the response, summarize:\n- files created\n- files modified\n- approximate lines added/removed\n- why each file changed\n- checks to run\n\nDo not make unrelated refactors.`,
    },
    {
      id: 'verify-polish',
      title: 'Verify and polish',
      summary: 'Use the current task to run checks, review UI/logic quality, and propose the next fix if something fails.',
      mode: 'code',
      impact: 'Focuses on correctness, build safety, and professional finish.',
      fileHint: 'Uses changed files and recent activity as context.',
      checkHint: 'Build, lint, typecheck, preview, or test depending on project signals.',
      prompt: `Verify and polish this work: ${task}\n\nCheck for:\n- build or TypeScript errors\n- UI overflow or bulky controls\n- missing states\n- risky file changes\n- next improvement with highest impact\n\nIf checks fail, explain the failure and prepare a small fix plan before patching.`,
    },
  ];
}
