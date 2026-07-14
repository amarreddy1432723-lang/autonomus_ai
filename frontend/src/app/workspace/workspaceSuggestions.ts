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
  confidence?: number;
  decisionReason?: string;
  tradeoffs?: string[];
  thinkingPrompt?: string;
  coachLens?: string[];
  alternatives?: string[];
  nextAfterDone?: string;
  description?: string;
  risk?: string;
  requiresApproval?: boolean;
  files?: string[];
  folders?: string[];
  steps?: string[];
  commands?: string[];
  expectedCommands?: string[];
  status?: string;
  createdAt?: string;
  updatedAt?: string;
  metadata?: Record<string, any>;
};

export function normalizeWorkspaceSuggestion(raw: any): WorkspaceSuggestion {
  return {
    id: String(raw?.id || `suggestion-${Date.now()}`),
    title: raw?.title || 'Workspace task',
    summary: raw?.summary || raw?.description || 'Suggested next action for this workspace.',
    description: raw?.description || raw?.summary || '',
    prompt: raw?.suggested_prompt || raw?.prompt || '',
    mode: (raw?.mode || 'code') as WorkspaceMode,
    impact: raw?.impact || '',
    fileHint: raw?.file_hint || raw?.fileHint || ((raw?.files || []).slice(0, 3).join(', ') || 'Workspace context'),
    checkHint: raw?.check_hint || raw?.checkHint || ((raw?.commands || raw?.expected_commands || []).slice(0, 2).join(', ') || 'Recommended checks'),
    confidence: typeof raw?.confidence === 'number' ? raw.confidence : undefined,
    decisionReason: raw?.decision_reason || raw?.decisionReason || '',
    tradeoffs: Array.isArray(raw?.tradeoffs) ? raw.tradeoffs : [],
    thinkingPrompt: raw?.thinking_prompt || raw?.thinkingPrompt || '',
    coachLens: Array.isArray(raw?.coach_lens) ? raw.coach_lens : Array.isArray(raw?.coachLens) ? raw.coachLens : [],
    alternatives: Array.isArray(raw?.alternatives) ? raw.alternatives : [],
    nextAfterDone: raw?.next_after_done || raw?.nextAfterDone || '',
    risk: raw?.risk || raw?.risk_level || 'medium',
    requiresApproval: Boolean(raw?.requires_approval ?? raw?.requiresApproval),
    files: Array.isArray(raw?.files) ? raw.files : [],
    folders: Array.isArray(raw?.folders) ? raw.folders : [],
    steps: Array.isArray(raw?.steps) ? raw.steps : [],
    commands: Array.isArray(raw?.commands) ? raw.commands : [],
    expectedCommands: Array.isArray(raw?.expected_commands) ? raw.expected_commands : Array.isArray(raw?.expectedCommands) ? raw.expectedCommands : [],
    status: raw?.status,
    createdAt: raw?.created_at || raw?.createdAt,
    updatedAt: raw?.updated_at || raw?.updatedAt,
    metadata: raw?.metadata || {},
  };
}

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
      confidence: 0.84,
      decisionReason: 'Planning first reduces rework when the goal is broad, unclear, or architecture-heavy.',
      tradeoffs: ['No immediate code output.', 'Creates clearer task boundaries before edits.'],
      thinkingPrompt: 'What should be true when this task is complete, and what files prove it?',
      coachLens: ['architecture', 'maintainability'],
      alternatives: ['Implement a reviewed patch now.', 'Verify the current workspace first.'],
      nextAfterDone: 'Convert the best step into a reviewed patch.',
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
      confidence: 0.78,
      decisionReason: 'This is the fastest useful path when the request is concrete enough for a narrow patch.',
      tradeoffs: ['Faster than planning.', 'May miss broader design concerns if the goal is vague.'],
      thinkingPrompt: 'What is the smallest useful change that proves progress?',
      coachLens: ['implementation', 'maintainability'],
      alternatives: ['Plan first.', 'Verify before editing.'],
      nextAfterDone: 'Review the diff and run the most relevant check.',
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
      confidence: 0.8,
      decisionReason: 'Verification turns the current workspace state into evidence before more work is stacked on top.',
      tradeoffs: ['Does not create a new feature directly.', 'Improves confidence and reduces regressions.'],
      thinkingPrompt: 'What signal proves this workspace is ready for the next task?',
      coachLens: ['reliability', 'quality'],
      alternatives: ['Review pending changes.', 'Implement the next small patch.'],
      nextAfterDone: 'Use the result to choose fix, test, or PR.',
      prompt: `Verify and polish this work: ${task}\n\nCheck for:\n- build or TypeScript errors\n- UI overflow or bulky controls\n- missing states\n- risky file changes\n- next improvement with highest impact\n\nIf checks fail, explain the failure and prepare a small fix plan before patching.`,
    },
  ];
}
