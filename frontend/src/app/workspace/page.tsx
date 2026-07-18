'use client';

import { Circle, MoreHorizontal, Settings, UserCircle } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import DesktopOnlyGuard from '../../components/DesktopOnlyGuard';
import ServiceRecoveryBanner from '../../components/ServiceRecoveryBanner';
import { ApiError, apiRequest, createApiHeadersAsync } from '../../utils/api';
import { probeServiceHealth, serviceHealthCopy, type ServiceHealthSnapshot } from '../../utils/serviceHealth';
import ActivityPanel, { ActivityEvent, AgentJob, GitHubBranch, GitHubRepository, GitHubStatus, PatchPreviewItem, PreviewCheck, PreviewLogs, RollbackSnapshot, RuntimeStatus, TerminalSession, WorkerStatus, WorkspaceAnalysis, WorkspaceCommand } from './ActivityPanel';
import ConversationPanel, { WorkspaceMessage, WorkspaceMode } from './ConversationPanel';
import EditorPanel, { OpenWorkspaceFile, WorkspaceDiagnostic } from './EditorPanel';
import type { EngineeringOrgState } from './EngineeringOrgPanel';
import ProjectNavigator from './ProjectNavigator';
import OnboardingWizard from './OnboardingWizard';
import FileExplorer, { WorkspaceFile, WorkspaceSearchMatch } from './FileExplorer';
import type { CompiledMissionPreview } from './MissionPreviewPanel';
import WorkspaceAppsPanel from './WorkspaceAppsPanel';
import WorkspaceSidebar, { WorkspaceRecentItem } from './WorkspaceSidebar';
import WorkspaceRightRail from './WorkspaceRightRail';
import WorkspaceTerminalPanel, { TerminalPanelSize } from './WorkspaceTerminalPanel';
import WorkspaceUpgradeDialog from './WorkspaceUpgradeDialog';
import { classifyError, type ClassifiedError } from './errorClassifier';
import type { WorkspaceWorkReceipt } from './WorkReceipt';
import styles from './Workspace.module.css';
import { buildWorkspaceSuggestions, normalizeWorkspaceSuggestion, WorkspaceSuggestion } from './workspaceSuggestions';
import {
  ACTIVE_PROJECT_KEY,
  CodeProject,
  MAX_OPEN_PROJECTS,
  OPEN_PROJECTS_KEY,
  PendingProjectOpen,
  TERMINAL_PREFS_KEY,
  WorkspaceCommandAction,
  WorkspaceRightPanelView,
  buildPreviewReceipt,
  buildWorkReceiptFromPayload,
  id,
  inferModes,
  inferReceiptIntent,
  model,
  normalizeEvents,
  promptTargetsActiveFile,
  summarizePatch,
  summarizePreview,
} from './workspacePageUtils';

type SafeApplyResult = {
  changed?: any[];
  remaining?: PatchPreviewItem[];
  impact?: any;
  review_required?: any[];
  conflicts?: any[];
  rollback_snapshot_id?: string | null;
  summary?: string;
  job?: AgentJob;
  work_receipt?: any;
};

export default function WorkspacePage() {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [jobs, setJobs] = useState<AgentJob[]>([]);
  const [workerStatus, setWorkerStatus] = useState<WorkerStatus | null>(null);
  const [commands, setCommands] = useState<WorkspaceCommand[]>([]);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [analysis, setAnalysis] = useState<WorkspaceAnalysis | null>(null);
  const [diagnostics, setDiagnostics] = useState<WorkspaceDiagnostic[]>([]);
  const [rollbackSnapshots, setRollbackSnapshots] = useState<RollbackSnapshot[]>([]);
  const [mode, setMode] = useState<WorkspaceMode>('auto');
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [upgradePrompt, setUpgradePrompt] = useState<any | null>(null);
  const [sessionId, setSessionId] = useState('');
  const [patchReady, setPatchReady] = useState(false);
  const [patchPreview, setPatchPreview] = useState<PatchPreviewItem[]>([]);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewLogs, setPreviewLogs] = useState<PreviewLogs | null>(null);
  const [previewChecks, setPreviewChecks] = useState<PreviewCheck[]>([]);
  const [repoUrl, setRepoUrl] = useState('');
  const [githubStatus, setGithubStatus] = useState<GitHubStatus | null>(null);
  const [githubRepositories, setGithubRepositories] = useState<GitHubRepository[]>([]);
  const [githubBranches, setGithubBranches] = useState<GitHubBranch[]>([]);
  const [selectedGithubRepo, setSelectedGithubRepo] = useState('');
  const [githubBaseBranch, setGithubBaseBranch] = useState('');
  const [githubBranchName, setGithubBranchName] = useState('');
  const [openTabs, setOpenTabs] = useState<OpenWorkspaceFile[]>([]);
  const [activeFileId, setActiveFileId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [searchMatches, setSearchMatches] = useState<WorkspaceSearchMatch[]>([]);
  const [searchFocusKey, setSearchFocusKey] = useState(0);
  const [filesOpen, setFilesOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [rightPanelView, setRightPanelView] = useState<WorkspaceRightPanelView>('explorer');
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [clientReady, setClientReady] = useState(false);
  const [terminalPanelOpen, setTerminalPanelOpen] = useState(false);
  const [terminalPanelSize, setTerminalPanelSize] = useState<TerminalPanelSize>('half');
  const [typedSuggestionId, setTypedSuggestionId] = useState('');
  const [backendSuggestions, setBackendSuggestions] = useState<WorkspaceSuggestion[]>([]);
  const [workspaceTasks, setWorkspaceTasks] = useState<WorkspaceSuggestion[]>([]);
  const [autoCompile, setAutoCompile] = useState(true);
  const [autoRunCommands, setAutoRunCommands] = useState(true);
  const [sandboxType, setSandboxType] = useState('local');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [agentOnline, setAgentOnline] = useState<boolean | null>(null);
  const [serviceHealth, setServiceHealth] = useState<ServiceHealthSnapshot>(() => {
    const copy = serviceHealthCopy('partially_online');
    return { state: 'partially_online', label: copy.label, detail: copy.detail, online: false, authReady: false, checkedAt: '' };
  });
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [projectId, setProjectId] = useState('');
  const [openProjectIds, setOpenProjectIds] = useState<string[]>([]);
  const [pendingProjectOpen, setPendingProjectOpen] = useState<PendingProjectOpen>(null);
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [localWorkspacePath, setLocalWorkspacePath] = useState('');
  const [localTreeFiles, setLocalTreeFiles] = useState<WorkspaceFile[]>([]);
  const [folderWatchError, setFolderWatchError] = useState<{ rootPath: string; message: string } | null>(null);
  const [engineeringOrgState, setEngineeringOrgState] = useState<EngineeringOrgState | null>(null);
  const [engineeringProblem, setEngineeringProblem] = useState('');
  const [terminalSessions, setTerminalSessions] = useState<Record<string, TerminalSession>>({});
  const [activeTerminalId, setActiveTerminalId] = useState('');
  const [terminalCommand, setTerminalCommand] = useState('');
  const [missionPreview, setMissionPreview] = useState<CompiledMissionPreview | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const lastAutoOpenedTerminalRef = useRef('');
  const autoCreatedTerminalRef = useRef('');
  const terminalStreamBufferRef = useRef<Record<string, Array<{ data: string; timestamp: string }>>>({});
  const terminalStreamFlushTimerRef = useRef<number | null>(null);
  const terminalLastSeqRef = useRef<Record<string, number>>({});
  const localWorkspacePathRef = useRef('');
  const directorySyncTimerRef = useRef<number | null>(null);
  const directorySyncQueueRef = useRef<any[]>([]);
  const directorySyncRunningRef = useRef(false);

  const selectedFileIds = useMemo(
    () => Object.entries(selected).filter(([, value]) => value).map(([fileId]) => fileId),
    [selected]
  );

  const activeProject = useMemo(
    () => projects.find((project) => project.id === projectId) || null,
    [projectId, projects]
  );

  const openProjects = useMemo(
    () => openProjectIds.map((idValue) => projects.find((project) => project.id === idValue)).filter(Boolean) as CodeProject[],
    [openProjectIds, projects]
  );

  const trustedLocalPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
  const normalizedTrustedLocalPath = trustedLocalPath.trim().toLowerCase().replace(/\\/g, '/').replace(/\/+$/, '');
  const engineeringDeliveryPackage = engineeringOrgState?.implementation_plan?.delivery_package || null;

  useEffect(() => {
    localWorkspacePathRef.current = trustedLocalPath;
  }, [trustedLocalPath]);

  useEffect(() => {
    if (openProjects.length === 0) {
      setOnboardingOpen(true);
    }
  }, [openProjects.length]);

  const handleOnboardingComplete = (settings: any) => {
    setOnboardingOpen(false);
    if (settings.mode === 'create') {
      void createProject();
    } else {
      void analyzeWorkspace();
    }
  };

  const sameLocalPath = (left?: string, right?: string) => {
    const normalize = (value?: string) => String(value || '').trim().toLowerCase().replace(/\\/g, '/').replace(/\/+$/, '');
    return Boolean(normalize(left) && normalize(left) === normalize(right));
  };

  const openRightTool = (view: typeof rightPanelView) => {
    setRightPanelView(view);
    setRightPanelOpen((current) => !(current && rightPanelView === view));
  };

  const rightDrawerInitialTab = (
    rightPanelView === 'changes' ? 'changes'
      : rightPanelView === 'jobs' ? 'jobs'
      : rightPanelView === 'preview' ? 'preview'
      : rightPanelView === 'git' ? 'git'
      : 'changes'
  ) as 'changes' | 'jobs' | 'preview' | 'git' | 'checks' | 'rollback';

  const canUseWorkspaceTerminal = !busy && (Boolean(trustedLocalPath) || agentOnline !== false);
  const terminalHelp = trustedLocalPath
    ? `Local terminal runs in ${trustedLocalPath}.`
    : agentOnline === false
      ? 'Open a folder to start local terminal, or start agent-service on port 8003 for cloud terminal.'
      : 'Open a folder for local terminal, or use backend workspace runtime.';

  const refreshServiceHealth = useCallback(async () => {
    if (typeof window === 'undefined') return;
    const snapshot = await probeServiceHealth();
    setServiceHealth(snapshot);
    setAgentOnline(snapshot.online);
  }, []);

  const startFolderWatch = (path: string) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    if (!path || !electron?.watchDirectory) return false;
    electron.watchDirectory(path);
    setFolderWatchError(null);
    return true;
  };

  const refreshLocalTree = useCallback(async (pathValue = trustedLocalPath) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    if (!pathValue || !electron?.readDirectoryTree) {
      setLocalTreeFiles([]);
      return;
    }
    try {
      const result = await electron.readDirectoryTree(pathValue);
      const items = Array.isArray(result?.items) ? result.items : [];
      setLocalTreeFiles(items.map((item: any) => ({
        id: `local-${item.type || 'file'}:${item.path}`,
        filename: String(item.path || '').replace(/\\/g, '/'),
        kind: item.type === 'folder' ? 'folder' : 'file',
        source: 'local',
        size_bytes: item.size_bytes,
      })).filter((item: WorkspaceFile) => item.filename));
    } catch (error) {
      setFolderWatchError({
        rootPath: pathValue,
        message: error instanceof Error ? error.message : 'Could not read the trusted folder tree.',
      });
    }
  }, [trustedLocalPath]);

  const retryFolderWatch = () => {
    const root = folderWatchError?.rootPath || trustedLocalPath;
    if (!root) return;
    if (startFolderWatch(root)) {
      addEvent({ kind: 'read', message: 'Retrying folder watcher', detail: root });
      void refreshLocalTree(root);
    }
  };

  const loadEngineeringOrg = useCallback(async (idValue = projectId) => {
    if (!idValue) {
      setEngineeringOrgState(null);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/projects/${idValue}/orchestration/state`);
      setEngineeringOrgState(data);
      if (!engineeringProblem && data?.original_problem) setEngineeringProblem(data.original_problem);
    } catch {
      setEngineeringOrgState(null);
    }
  }, [engineeringProblem, projectId]);

  const analyzeEngineeringProblem = async () => {
    if (!projectId || busy || engineeringProblem.trim().length < 3) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/analyze`, {
        method: 'POST',
        body: JSON.stringify({
          problem: engineeringProblem.trim(),
          acceptance_criteria: [
            'A user can complete the core workflow end to end.',
            'Changes are reviewable before approval.',
            'Focused build or validation checks can run.',
          ],
        }),
      });
      setEngineeringOrgState(data);
      setRightPanelView('org');
      setRightPanelOpen(true);
      addEvent({ kind: 'code', message: 'Engineering proposals ready', detail: 'Three senior perspectives were scored for this project.' });
    } catch (error) {
      reportWorkspaceError(error, 'Engineering proposal generation failed');
    } finally {
      setBusy(false);
    }
  };

  const selectEngineeringProposal = async (proposalId: string) => {
    if (!projectId || busy || !proposalId) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/proposals/${proposalId}/select`, {
        method: 'POST',
        body: JSON.stringify({ rationale: 'Selected from the Arceus Engineering Org proposal panel.' }),
      });
      setEngineeringOrgState(data);
      addEvent({ kind: 'done', message: 'Engineering proposal selected', detail: 'Architecture and first task graph are ready for approval.' });
    } catch (error) {
      reportWorkspaceError(error, 'Proposal selection failed');
    } finally {
      setBusy(false);
    }
  };

  const approveEngineeringArchitecture = async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/architecture/approve`, {
        method: 'POST',
        body: JSON.stringify({ approved: true, notes: 'Approved from Arceus workspace.' }),
      });
      setEngineeringOrgState(data);
      addEvent({ kind: 'done', message: 'Architecture approved', detail: 'The project is ready for bounded implementation tasks.' });
    } catch (error) {
      reportWorkspaceError(error, 'Architecture approval failed');
    } finally {
      setBusy(false);
    }
  };

  const materializeEngineeringTasks = async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/tasks/materialize`, {
        method: 'POST',
      });
      setEngineeringOrgState(data.orchestration);
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem('nexus.code.session_id', data.session_id);
      }
      const syncedTasks: WorkspaceSuggestion[] = (data.workspace_tasks || []).map(normalizeWorkspaceSuggestion);
      if (syncedTasks.length) {
        setWorkspaceTasks((current) => {
          const ids = new Set(syncedTasks.map((task) => task.id));
          return [...syncedTasks, ...current.filter((task) => !ids.has(task.id))].slice(0, 20);
        });
      }
      setRightPanelView('tasks');
      setRightPanelOpen(true);
      addEvent({ kind: 'code', message: 'Engineering tasks synced', detail: `${syncedTasks.length} execution task(s) are now in the task rail.` });
    } catch (error) {
      reportWorkspaceError(error, 'Engineering task sync failed');
    } finally {
      setBusy(false);
    }
  };

  const typeEngineeringTask = async (taskIdValue: string) => {
    if (!projectId || busy || !taskIdValue) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/tasks/type`, {
        method: 'POST',
        body: JSON.stringify({ task_id: taskIdValue, status: 'typed' }),
      });
      setEngineeringOrgState(data.orchestration);
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem('nexus.code.session_id', data.session_id);
      }
      const normalized = normalizeWorkspaceSuggestion(data.workspace_task);
      setPrompt(normalized.prompt);
      setMode(normalized.mode);
      setTypedSuggestionId(normalized.id);
      setWorkspaceTasks((current) => [normalized, ...current.filter((task) => task.id !== normalized.id)].slice(0, 20));
      setRightPanelView('tasks');
      setRightPanelOpen(true);
      addEvent({ kind: 'code', message: `Typed engineering task: ${normalized.title}`, detail: normalized.summary });
    } catch (error) {
      reportWorkspaceError(error, 'Engineering task handoff failed');
    } finally {
      setBusy(false);
    }
  };

  const syncEngineeringProgress = async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/tasks/sync-progress`, {
        method: 'POST',
      });
      setEngineeringOrgState(data.orchestration);
      addEvent({
        kind: 'code',
        message: 'Engineering progress synced',
        detail: `${data.progress?.completed || 0}/${data.progress?.total || 0} task(s) done, ${data.progress?.waiting_approval || 0} waiting approval.`,
      });
    } catch (error) {
      reportWorkspaceError(error, 'Engineering progress sync failed');
    } finally {
      setBusy(false);
    }
  };

  const runEngineeringReviewBoard = async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/review-board`, {
        method: 'POST',
        body: JSON.stringify({ approve_ready: false }),
      });
      setEngineeringOrgState(data.orchestration);
      addEvent({
        kind: data.blockers ? 'error' : 'done',
        message: 'Review board complete',
        detail: `${data.findings?.length || 0} finding(s), ${data.blockers || 0} blocker(s), ${data.warnings || 0} warning(s).`,
      });
    } catch (error) {
      reportWorkspaceError(error, 'Engineering review board failed');
    } finally {
      setBusy(false);
    }
  };

  const prepareEngineeringDelivery = async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/code/projects/${projectId}/orchestration/delivery-package`, {
        method: 'POST',
        body: JSON.stringify({ target: 'pull_request', include_release_notes: true }),
      });
      setEngineeringOrgState(data.orchestration);
      addEvent({
        kind: data.delivery_package?.ready ? 'done' : 'code',
        message: 'Delivery package prepared',
        detail: `${data.delivery_package?.title || 'PR package'} · ${data.delivery_package?.impact?.files_changed || 0} file(s).`,
      });
      setRightPanelOpen(true);
      setRightPanelView('git');
    } catch (error) {
      reportWorkspaceError(error, 'Delivery package preparation failed');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!trustedLocalPath) {
      setLocalTreeFiles([]);
      return;
    }
    void refreshLocalTree(trustedLocalPath);
  }, [refreshLocalTree, trustedLocalPath]);

  useEffect(() => {
    void loadEngineeringOrg(projectId);
  }, [loadEngineeringOrg, projectId]);

  const persistOpenProjects = (nextIds: string[], activeId?: string) => {
    const unique = nextIds.filter((idValue, index) => idValue && nextIds.indexOf(idValue) === index).slice(0, MAX_OPEN_PROJECTS);
    setOpenProjectIds(unique);
    try {
      localStorage.setItem(OPEN_PROJECTS_KEY, JSON.stringify(unique));
      if (activeId !== undefined) {
        if (activeId) localStorage.setItem(ACTIVE_PROJECT_KEY, activeId);
        else localStorage.removeItem(ACTIVE_PROJECT_KEY);
      }
    } catch {
      // Project tabs remain in memory if localStorage is unavailable.
    }
    return unique;
  };

  const canOpenProjectNow = (idValue: string) => openProjectIds.includes(idValue) || openProjectIds.length < MAX_OPEN_PROJECTS;

  const rememberOpenProject = (idValue: string) => {
    setOpenProjectIds((current) => {
      const next = [idValue, ...current.filter((item) => item !== idValue)].slice(0, MAX_OPEN_PROJECTS);
      try {
        localStorage.setItem(OPEN_PROJECTS_KEY, JSON.stringify(next));
        localStorage.setItem(ACTIVE_PROJECT_KEY, idValue);
      } catch {
        // In-memory project switcher still works.
      }
      return next;
    });
  };

  const localSuggestions = useMemo(
    () => buildWorkspaceSuggestions(prompt, mode, selectedFileIds.length),
    [mode, prompt, selectedFileIds.length]
  );

  const suggestions = useMemo(
    () => (backendSuggestions.length ? backendSuggestions : localSuggestions),
    [backendSuggestions, localSuggestions]
  );

  const taskRailItems = useMemo(
    () => (workspaceTasks.length ? workspaceTasks : suggestions),
    [suggestions, workspaceTasks]
  );

  const activeSuggestion = useMemo(() => {
    return taskRailItems.find((item) => item.id === typedSuggestionId) || taskRailItems[0] || null;
  }, [taskRailItems, typedSuggestionId]);

  const navigatorTask = useMemo(() => {
    if (!activeSuggestion) return null;
    return {
      id: activeSuggestion.id,
      objective: activeProject?.description || 'Implement developer requests in the current workspace',
      recommendedTask: activeSuggestion.title,
      reason: activeSuggestion.decisionReason || activeSuggestion.summary,
      risks: activeSuggestion.risk || 'No critical architectural risks detected.',
      suggestedActions: activeSuggestion.steps && activeSuggestion.steps.length > 0
        ? activeSuggestion.steps
        : [activeSuggestion.summary],
      manualSteps: activeSuggestion.tradeoffs && activeSuggestion.tradeoffs.length > 0
        ? activeSuggestion.tradeoffs
        : ['Locate the target files in the explorer panel.', 'Read through functions and dependencies.', 'Perform the requested edit manually.', 'Run local test suites to verify compile correctness.'],
      automatedPrompt: activeSuggestion.prompt
    };
  }, [activeSuggestion, activeProject]);


  useEffect(() => {
    try {
      const raw = localStorage.getItem('nexus.code.preferences');
      if (!raw) return;
      const preferences = JSON.parse(raw);
      if (preferences.mode) setMode(preferences.mode);
      if (typeof preferences.autoCompile === 'boolean') setAutoCompile(preferences.autoCompile);
      if (typeof preferences.autoRunCommands === 'boolean') setAutoRunCommands(preferences.autoRunCommands);
      if (typeof preferences.sandboxType === 'string') setSandboxType(preferences.sandboxType);
    } catch {
      // Preferences are optional and should never block the workspace.
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('nexus.code.preferences', JSON.stringify({
        mode,
        autoCompile,
        autoRunCommands,
        sandboxType,
        approvalStyle: 'review-first',
        verbosity: 'concise',
      }));
    } catch {
      // Ignore localStorage failures.
    }
  }, [autoCompile, autoRunCommands, mode, sandboxType]);

  useEffect(() => {
    let cancelled = false;
    const checkAgentHealth = async () => {
      if (cancelled) return;
      await refreshServiceHealth();
    };
    void checkAgentHealth();
    const timer = window.setInterval(checkAgentHealth, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refreshServiceHealth]);

  useEffect(() => {
    const handleTerminalShortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === '`') {
        event.preventDefault();
        setTerminalPanelOpen((current) => !current);
      }
    };
    window.addEventListener('keydown', handleTerminalShortcut);
    return () => window.removeEventListener('keydown', handleTerminalShortcut);
  }, []);

  useEffect(() => {
    setClientReady(true);
    try {
      const value = JSON.parse(localStorage.getItem(TERMINAL_PREFS_KEY) || '{}');
      setTerminalPanelOpen(value?.open === true);
      setTerminalPanelSize(value?.size === 'compact' || value?.size === 'half' || value?.size === 'max' ? value.size : 'half');
    } catch {
      setTerminalPanelOpen(false);
      setTerminalPanelSize('half');
    }
  }, []);

  useEffect(() => {
    if (!clientReady) return;
    try {
      localStorage.setItem(TERMINAL_PREFS_KEY, JSON.stringify({
        open: terminalPanelOpen,
        size: terminalPanelSize,
      }));
    } catch {
      // Terminal layout preference is optional.
    }
  }, [clientReady, terminalPanelOpen, terminalPanelSize]);

  useEffect(() => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    if (!electron?.onTerminalData) return;
    const flushTerminalStream = () => {
      const batches = terminalStreamBufferRef.current;
      terminalStreamBufferRef.current = {};
      terminalStreamFlushTimerRef.current = null;
      const entries = Object.entries(batches);
      if (!entries.length) return;
      setTerminalSessions((current) => {
        let next = current;
        for (const [terminalId, chunks] of entries) {
          if (!chunks.length) continue;
          const latest = chunks[chunks.length - 1];
          const existing = next[terminalId] || {
            id: terminalId,
            status: 'active',
            cwd: localWorkspacePathRef.current,
            history: [],
            logs: [],
            created_at: latest.timestamp,
          };
          const combined = chunks.map((chunk) => chunk.data).join('');
          next = {
            ...next,
            [terminalId]: {
              ...existing,
              status: existing.status === 'killed' ? existing.status : 'active',
              logs: [
                ...(existing.logs || []),
                {
                  status: 'stream',
                  output_excerpt: combined,
                  updated_at: latest.timestamp,
                  source: 'electron-pty',
                },
              ].slice(-160),
              updated_at: latest.timestamp,
            },
          };
        }
        return next;
      });
    };
    const unsubscribeData = electron.onTerminalData((payload: any) => {
      if (!payload?.id) return;
      const terminalId = String(payload.id);
      const seq = Number(payload.seq || 0);
      if (seq > 0) {
        const previousSeq = terminalLastSeqRef.current[terminalId] || 0;
        if (seq <= previousSeq) return;
        terminalLastSeqRef.current[terminalId] = seq;
      }
      terminalStreamBufferRef.current[terminalId] = [
        ...(terminalStreamBufferRef.current[terminalId] || []),
        { data: String(payload.data || ''), timestamp: payload.timestamp || new Date().toISOString() },
      ];
      if (terminalStreamFlushTimerRef.current === null) {
        terminalStreamFlushTimerRef.current = window.setTimeout(flushTerminalStream, 50);
      }
    });
    const unsubscribeExit = electron.onTerminalExit?.((payload: any) => {
      if (!payload?.id) return;
      setTerminalSessions((current) => {
        const existing = current[payload.id];
        if (!existing) return current;
        const wasInterrupted = Number(payload.code) === -1073741510;
        const status = payload.signal === 'killed' ? 'killed' : wasInterrupted ? 'interrupted' : 'exited';
        const message = payload.signal === 'killed'
          ? 'Terminal killed.'
          : wasInterrupted
            ? 'Terminal interrupted by Ctrl+C/control-break.'
            : `Terminal exited${typeof payload.code === 'number' ? ` with code ${payload.code}` : ''}.`;
        return {
          ...current,
          [payload.id]: {
            ...existing,
            status,
            logs: [
              ...(existing.logs || []),
              {
                status,
                output_excerpt: message,
                updated_at: payload.timestamp,
                source: 'electron-pty',
              },
            ].slice(-160),
            updated_at: payload.timestamp,
          },
        };
      });
    });
    return () => {
      if (terminalStreamFlushTimerRef.current !== null) {
        window.clearTimeout(terminalStreamFlushTimerRef.current);
        terminalStreamFlushTimerRef.current = null;
      }
      terminalStreamBufferRef.current = {};
      terminalLastSeqRef.current = {};
      unsubscribeData?.();
      unsubscribeExit?.();
    };
  }, []);

  useEffect(() => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    if (!electron?.onFolderWatchError) return;
    const unsubscribe = electron.onFolderWatchError((payload: any) => {
      const root = payload?.rootPath || trustedLocalPath || 'workspace folder';
      setFolderWatchError({
        rootPath: root,
        message: payload?.message || 'The folder watcher could not read part of this workspace.',
      });
      addEvent({
        kind: 'error',
        message: 'Folder watcher paused',
        detail: `${payload?.message || 'The folder watcher could not read part of this workspace.'} Retry by reopening Explorer or the folder. (${root})`,
      });
    });
    return () => unsubscribe?.();
  }, [trustedLocalPath]);

  const openFile = useMemo(
    () => openTabs.find((file) => file.id === activeFileId) || openTabs[0] || null,
    [activeFileId, openTabs]
  );

  const visibleFiles = useMemo(
    () => {
      if (!localTreeFiles.length) return files;
      const byPath = new Map(files.map((file) => [file.filename.replace(/\\/g, '/').toLowerCase(), file]));
      const localOnly = localTreeFiles.filter((file) => !byPath.has(file.filename.replace(/\\/g, '/').toLowerCase()));
      return [...files, ...localOnly];
    },
    [files, localTreeFiles]
  );

  const recentItems = useMemo<WorkspaceRecentItem[]>(() => {
    const projectItems = openProjects.map((project) => ({
      id: `project-${project.id}`,
      label: project.name,
      detail: project.local_workspace_path || project.repo_url || `${project.file_count ?? project.file_ids?.length ?? 0} file${(project.file_count ?? project.file_ids?.length) === 1 ? '' : 's'}`,
      kind: 'project' as const,
    }));
    const taskItems = workspaceTasks.slice(0, 4).map((task) => ({
      id: `task-${task.id}`,
      label: task.title,
      detail: task.status || task.mode || 'task',
      kind: 'task' as const,
    }));
    return [...projectItems, ...taskItems].slice(0, 8);
  }, [openProjects, workspaceTasks]);

  const addEvent = (event: Omit<ActivityEvent, 'id'>) => {
    setEvents((current) => [{ ...event, id: id('evt') }, ...current].slice(0, 80));
  };

  const addMessage = (role: WorkspaceMessage['role'], content: string, receipt?: WorkspaceWorkReceipt) => {
    setMessages((current) => [...current, { id: id(role), role, content, receipt }]);
  };

  const selectedWorkspaceFilenames = (fileIds = selectedFileIds) => {
    const selectedSet = new Set(fileIds);
    return files.filter((file) => selectedSet.has(file.id)).map((file) => file.filename);
  };

  const resolveEffectiveFileIds = (value: string) => {
    const ids = new Set(selectedFileIds);
    if (promptTargetsActiveFile(value) && openFile?.id) {
      ids.add(openFile.id);
    }
    return Array.from(ids);
  };

  const buildReceipt = ({
    summary,
    receiptMode,
    intent,
    plan,
    preview,
    commandsRun = [],
    checks = [],
    nextActions = [],
    approvalState,
    contextFileIds,
  }: {
    summary: string;
    receiptMode: WorkspaceWorkReceipt['mode'];
    intent: string;
    plan?: string;
    preview?: any[];
    commandsRun?: Array<{ label: string; status?: string }>;
    checks?: Array<{ label: string; status?: string }>;
    nextActions?: WorkspaceSuggestion[];
    approvalState?: string;
    contextFileIds?: string[];
  }): WorkspaceWorkReceipt => ({
    summary,
    mode: receiptMode,
    intent,
    project: activeProject?.name || 'Workspace',
    session: sessionId ? sessionId.slice(0, 8) : undefined,
    plan,
    filesInspected: selectedWorkspaceFilenames(contextFileIds),
    filesChanged: (preview || []).map((item) => ({
      filename: item.filename || item.new_filename || item.file_id || 'workspace file',
      operation: item.operation || item.type || 'modify',
      additions: item.additions || 0,
      deletions: item.deletions || 0,
    })),
    foldersCreated: (preview || []).filter((item) => (item.operation || item.type) === 'folder').map((item) => item.filename),
    commands: commandsRun.length ? commandsRun : commands.slice(0, 4).map((command) => ({ label: command.command || command.label, status: 'recommended' })),
    checks,
    checksPassed: checks.filter((check) => /pass|success|done|completed/i.test(check.status || '')).length,
    checksFailed: checks.filter((check) => /fail|error|blocked|timeout/i.test(check.status || '')).length,
    approvalState,
    lineImpact: {
      additions: (preview || []).reduce((total, item) => total + (item.additions || 0), 0),
      deletions: (preview || []).reduce((total, item) => total + (item.deletions || 0), 0),
    },
    nextActions: nextActions.slice(0, 3),
  });

  const buildErrorReceipt = (classified: ClassifiedError, intent = inferReceiptIntent(prompt || mode)): WorkspaceWorkReceipt => ({
    summary: classified.message,
    mode: 'error',
    intent,
    project: activeProject?.name || 'Workspace',
    session: sessionId ? sessionId.slice(0, 8) : undefined,
    plan: classified.hint,
    filesInspected: selectedWorkspaceFilenames(),
    filesChanged: [],
    commands: [],
    checks: [{ label: classified.class, status: 'failed' }],
    checksPassed: 0,
    checksFailed: 1,
    approvalState: 'failed',
    lineImpact: { additions: 0, deletions: 0 },
    nextActions: suggestions.slice(0, 3),
    errorClass: classified.class,
    errorHint: classified.hint,
    rawError: classified.raw,
  });

  const reportWorkspaceError = (error: unknown, fallbackMessage: string, options: { chat?: boolean; intent?: string } = {}) => {
    const classified = classifyError(error);
    addEvent({
      kind: 'error',
      message: classified.message || fallbackMessage,
      detail: classified.hint,
      errorClass: classified.class,
      raw: classified.raw,
    } as ActivityEvent & { errorClass?: string; raw?: string });
    if (options.chat) {
      addMessage(
        'assistant',
        `${classified.message}\n\n${classified.hint}${classified.raw ? `\n\nDetails: ${classified.raw}` : ''}`,
        buildErrorReceipt(classified, options.intent || fallbackMessage)
      );
    }
    return classified;
  };

  const updateOpenTab = (fileId: string, updater: (file: OpenWorkspaceFile) => OpenWorkspaceFile) => {
    setOpenTabs((current) => current.map((file) => file.id === fileId ? updater(file) : file));
  };

  const closeOpenTab = (fileId: string) => {
    setOpenTabs((current) => {
      const index = current.findIndex((file) => file.id === fileId);
      const next = current.filter((file) => file.id !== fileId);
      if (activeFileId === fileId) {
        const fallback = next[Math.max(0, index - 1)] || next[0];
        setActiveFileId(fallback?.id || '');
      }
      return next;
    });
  };

  const focusWorkspaceSearch = () => {
    setFilesOpen(true);
    setSearchFocusKey((current) => current + 1);
  };

  const resetWorkspaceForProject = () => {
    localStorage.removeItem('nexus.code.session_id');
    setSessionId('');
    setProjectId('');
    setSelected({});
    setMessages([]);
    setEvents([]);
    setJobs([]);
    setCommands([]);
    setRuntimeStatus(null);
    setAnalysis(null);
    setRollbackSnapshots([]);
    setPatchPreview([]);
    setPatchReady(false);
    setPreviewChecks([]);
    setPreviewLogs(null);
    setGithubStatus(null);
    setGithubRepositories([]);
    setSelectedGithubRepo('');
    setGithubBranchName('');
    setLocalWorkspacePath('');
    setTerminalSessions({});
    setActiveTerminalId('');
    setTerminalCommand('');
    setOpenTabs([]);
    setActiveFileId('');
    setSearchMatches([]);
    setBackendSuggestions([]);
    setWorkspaceTasks([]);
  };

  const createProject = async (providedName?: string) => {
    if (busy) return;
    const fallbackName = `Arceus Code Project ${new Date().toLocaleDateString()}`;
    const name = providedName?.trim() || fallbackName;
    setBusy(true);
    try {
      resetWorkspaceForProject();
      const project = await apiRequest('/api/v1/code/projects', {
        method: 'POST',
        body: JSON.stringify({ name, file_ids: [] }),
      });
      setProjectId(project.id);
      rememberOpenProject(project.id);
      if (project.session?.id) {
        setSessionId(project.session.id);
        localStorage.setItem('nexus.code.session_id', project.session.id);
      }
      await loadProjects();
      addEvent({ kind: 'start', message: 'Code project created', detail: name });
      setFilesOpen(true);
      setTimeout(() => fileInputRef.current?.click(), 0);
    } catch (error) {
      reportWorkspaceError(error, 'Create project failed');
    } finally {
      setBusy(false);
    }
  };

  const importLocalDirectory = async (localPath: string, forceOpen = false) => {
    if (busy) return;
    const existingProject = projects.find((project) => project.local_workspace_path === localPath || project.metadata?.local_workspace_path === localPath);
    if (!forceOpen && existingProject && !canOpenProjectNow(existingProject.id)) {
      setPendingProjectOpen({ kind: 'local', localPath });
      return;
    }
    if (!forceOpen && !existingProject && openProjectIds.length >= MAX_OPEN_PROJECTS) {
      setPendingProjectOpen({ kind: 'local', localPath });
      return;
    }
    setBusy(true);
    try {
      if (!existingProject) {
        try {
          const linkedProject = await apiRequest(`/api/v1/code/projects/by-path?path=${encodeURIComponent(localPath)}`);
          if (linkedProject?.id) {
            setProjects((current) => [linkedProject, ...current.filter((project) => project.id !== linkedProject.id)]);
            if (!forceOpen && !canOpenProjectNow(linkedProject.id)) {
              setPendingProjectOpen({ kind: 'project', projectId: linkedProject.id });
              return;
            }
            resetWorkspaceForProject();
            setProjectId(linkedProject.id);
            const trustedPath = linkedProject.local_workspace_path || linkedProject.metadata?.local_workspace_path || localPath;
            setLocalWorkspacePath(trustedPath);
            rememberOpenProject(linkedProject.id);
            setSelected(Object.fromEntries((linkedProject.file_ids || []).map((fileId: string) => [fileId, true])));
            startFolderWatch(trustedPath);
            if (linkedProject.active_session_id) {
              localStorage.setItem('nexus.code.session_id', linkedProject.active_session_id);
              await hydrateSession(linkedProject.active_session_id);
            }
            await loadProjects();
            addEvent({ kind: 'read', message: `Reopened ${linkedProject.name}`, detail: trustedPath });
            return;
          }
        } catch {
          // No linked project exists yet; import below will create one.
        }
      }
      resetWorkspaceForProject();
      const session = await apiRequest('/api/v1/code/sessions/import-local', {
        method: 'POST',
        body: JSON.stringify({ local_path: localPath }),
      });
      setProjectId(session.project_id);
      setSessionId(session.id);
      setLocalWorkspacePath(localPath);
      if (session.project_id) rememberOpenProject(session.project_id);
      localStorage.setItem('nexus.code.session_id', session.id);
      startFolderWatch(localPath);
      await loadProjects();
      addEvent({ kind: 'start', message: 'Local directory imported', detail: localPath });
      await hydrateSession(session.id);
    } catch (error) {
      reportWorkspaceError(error, 'Import local directory failed');
    } finally {
      setBusy(false);
    }
  };

  const loadProjects = async () => {
    try {
      const data = await apiRequest('/api/v1/code/projects');
      setProjects(data || []);
    } catch {
      setProjects([]);
    }
  };

  const openCodeProject = async (idValue: string, forceOpen = false) => {
    if (busy) return;
    if (!forceOpen && !canOpenProjectNow(idValue)) {
      setPendingProjectOpen({ kind: 'project', projectId: idValue });
      return;
    }
    setBusy(true);
    try {
      const project = await apiRequest(`/api/v1/code/projects/${idValue}`);
      setProjectId(project.id);
      const trustedPath = project.local_workspace_path || project.metadata?.local_workspace_path || '';
      setLocalWorkspacePath(trustedPath);
      startFolderWatch(trustedPath);
      rememberOpenProject(project.id);
      const fileIds = project.file_ids || [];
      setSelected(Object.fromEntries(fileIds.map((fileId: string) => [fileId, true])));
      if (project.active_session_id) {
        localStorage.setItem('nexus.code.session_id', project.active_session_id);
        await hydrateSession(project.active_session_id);
      } else {
        const session = await apiRequest('/api/v1/code/sessions', {
          method: 'POST',
          body: JSON.stringify({ title: `${project.name} workspace`, file_ids: fileIds, project_id: project.id }),
        });
        setSessionId(session.id);
        localStorage.setItem('nexus.code.session_id', session.id);
        await hydrateSession(session.id);
      }
      await loadProjects();
      addEvent({ kind: 'read', message: `Opened ${project.name}`, detail: `${fileIds.length} project file(s) linked.` });
    } catch (error) {
      reportWorkspaceError(error, 'Open project failed');
    } finally {
      setBusy(false);
    }
  };

  const openRecent = (item: WorkspaceRecentItem) => {
    if (item.kind === 'project') {
      void openCodeProject(item.id.replace(/^project-/, ''));
      return;
    }
    if (item.kind === 'file') {
      const file = files.find((candidate) => `file-${candidate.id}` === item.id);
      if (file) void openWorkspaceFile(file);
      return;
    }
    focusWorkspaceSearch();
  };

  const closeProjectTab = (idValue: string) => {
    const next = openProjectIds.filter((item) => item !== idValue);
    persistOpenProjects(next, projectId === idValue ? next[0] || '' : projectId);
    setMergeSelection((current) => current.filter((item) => item !== idValue));
    if (projectId === idValue) {
      if (next[0]) void openCodeProject(next[0]);
      else resetWorkspaceForProject();
    }
  };

  const removeProjectFromApp = async (idValue: string) => {
    const project = projects.find((item) => item.id === idValue);
    const ok = window.confirm(`Remove ${project?.name || 'this project'} from Arceus? This does not delete the folder from your computer.`);
    if (!ok) return;
    try {
      await apiRequest(`/api/v1/code/projects/${idValue}`, { method: 'DELETE' });
      const next = openProjectIds.filter((item) => item !== idValue);
      persistOpenProjects(next, projectId === idValue ? next[0] || '' : projectId);
      setProjects((current) => current.filter((item) => item.id !== idValue));
      setMergeSelection((current) => current.filter((item) => item !== idValue));
      if (projectId === idValue) {
        if (next[0]) void openCodeProject(next[0]);
        else resetWorkspaceForProject();
      }
      addEvent({ kind: 'done', message: 'Project removed from app', detail: project?.name || idValue });
    } catch (error) {
      reportWorkspaceError(error, 'Remove project failed');
    }
  };

  const toggleMergeProject = (idValue: string) => {
    setMergeSelection((current) => {
      if (current.includes(idValue)) return current.filter((item) => item !== idValue);
      return [...current, idValue].slice(-2);
    });
  };

  const mergeSelectedProjects = async () => {
    if (mergeSelection.length !== 2 || busy) return;
    setBusy(true);
    try {
      const first = projects.find((project) => project.id === mergeSelection[0]);
      const second = projects.find((project) => project.id === mergeSelection[1]);
      const merged = await apiRequest('/api/v1/code/projects/merge', {
        method: 'POST',
        body: JSON.stringify({
          source_project_ids: mergeSelection,
          name: first && second ? `Merged: ${first.name} + ${second.name}` : undefined,
        }),
      });
      await loadProjects();
      setMergeSelection([]);
      rememberOpenProject(merged.id);
      if (merged.session?.id) {
        localStorage.setItem('nexus.code.session_id', merged.session.id);
        await hydrateSession(merged.session.id);
      } else {
        await openCodeProject(merged.id);
      }
      addEvent({
        kind: 'done',
        message: 'Merged project created',
        detail: `${merged.merge?.copied?.length || 0} files copied. Originals were not changed.`,
      });
    } catch (error) {
      reportWorkspaceError(error, 'Merge projects failed');
    } finally {
      setBusy(false);
    }
  };

  const replaceOpenProject = async (closeId: string) => {
    const next = openProjectIds.filter((item) => item !== closeId);
    persistOpenProjects(next, projectId === closeId ? '' : projectId);
    const pending = pendingProjectOpen;
    setPendingProjectOpen(null);
    if (!pending) return;
    if (pending.kind === 'project') {
      await openCodeProject(pending.projectId, true);
    } else {
      await importLocalDirectory(pending.localPath, true);
    }
  };

  const newChat = async () => {
    if (busy) return;
    if (!projectId || !activeProject) {
      addEvent({ kind: 'error', message: 'Open a project first', detail: 'New chats are scoped to a project folder.' });
      return;
    }
    setBusy(true);
    try {
      const session = await apiRequest(`/api/v1/code/projects/${projectId}/sessions`, {
        method: 'POST',
        body: JSON.stringify({
          title: `${activeProject.name} chat`,
          file_ids: activeProject.file_ids || selectedFileIds,
          project_id: projectId,
        }),
      });
      setMessages([]);
      setPrompt('');
      setTypedSuggestionId('');
      setBackendSuggestions([]);
      setSessionId(session.id);
      localStorage.setItem('nexus.code.session_id', session.id);
      await hydrateSession(session.id);
      addEvent({ kind: 'start', message: 'Project chat started', detail: `${activeProject.name} only.` });
    } catch (error) {
      reportWorkspaceError(error, 'New chat failed');
    } finally {
      setBusy(false);
    }
  };

  const updatePrompt = (value: string) => {
    setPrompt(value);
    setTypedSuggestionId('');
  };

  const refreshWorkspaceTasks = async (idValue = sessionId) => {
    if (!idValue) return;
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/tasks`);
      setWorkspaceTasks((data.tasks || []).map(normalizeWorkspaceSuggestion));
    } catch {
      // Task rail falls back to live suggestions when task persistence is unavailable.
    }
  };

  const fetchBackendSuggestions = async (value: string, currentMode: WorkspaceMode, idValue = sessionId) => {
    const trimmed = value.trim();
    if (!trimmed || !idValue) {
      setBackendSuggestions([]);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/suggest-next`, {
        method: 'POST',
        body: JSON.stringify({
          user_description: trimmed,
          selected_mode: currentMode,
          selected_file_ids: resolveEffectiveFileIds(trimmed),
          open_file_ids: openTabs.map((file) => file.id),
          current_prompt: trimmed,
          recent_messages: messages.slice(-6).map((message) => ({ role: message.role, content: message.content.slice(0, 1000) })),
        }),
      });
      setBackendSuggestions((data.suggestions || []).map(normalizeWorkspaceSuggestion));
    } catch {
      setBackendSuggestions([]);
    }
  };

  const typeSuggestion = async (suggestion: WorkspaceSuggestion) => {
    setPrompt(suggestion.prompt);
    setMode(suggestion.mode);
    setRightPanelView('tasks');
    setRightPanelOpen(true);
    try {
      const sid = await ensureSession();
      const task = await apiRequest(`/api/v1/code/sessions/${sid}/tasks`, {
        method: 'POST',
        body: JSON.stringify({
          id: suggestion.id,
          title: suggestion.title,
          description: suggestion.description || suggestion.summary,
          summary: suggestion.summary,
          mode: suggestion.mode,
          status: 'typed',
          risk: suggestion.risk || 'medium',
          requires_approval: Boolean(suggestion.requiresApproval),
          files: suggestion.files || [],
          folders: suggestion.folders || [],
          steps: suggestion.steps || [],
          commands: suggestion.commands || suggestion.expectedCommands || [],
          expected_commands: suggestion.expectedCommands || suggestion.commands || [],
          suggested_prompt: suggestion.prompt,
          impact: suggestion.impact,
          file_hint: suggestion.fileHint,
          check_hint: suggestion.checkHint,
          confidence: suggestion.confidence,
          decision_reason: suggestion.decisionReason,
          tradeoffs: suggestion.tradeoffs || [],
          thinking_prompt: suggestion.thinkingPrompt,
          coach_lens: suggestion.coachLens || [],
          alternatives: suggestion.alternatives || [],
          next_after_done: suggestion.nextAfterDone,
        }),
      });
      const normalized = normalizeWorkspaceSuggestion(task);
      setTypedSuggestionId(normalized.id);
      setWorkspaceTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)].slice(0, 20));
      addEvent({ kind: 'code', message: `Typed task: ${normalized.title}`, detail: normalized.summary });
    } catch {
      setTypedSuggestionId(suggestion.id);
    }
  };

  const loadFiles = async () => {
    try {
      const data = await apiRequest('/api/v1/files');
      setFiles(data);
    } catch {
      setFiles([]);
    }
  };

  const hydrateSession = async (idValue: string) => {
    if (!idValue) return;
    try {
      const session = await apiRequest(`/api/v1/code/sessions/${idValue}`);
      setSessionId(session.id);
      setProjectId(session.project_id || '');
      if (session.project_id) rememberOpenProject(session.project_id);
      setLocalWorkspacePath(session.metadata_json?.local_workspace_path || '');
      const hydratedTerminals = session.metadata_json?.terminal_sessions || {};
      setTerminalSessions(hydratedTerminals);
      const firstTerminalId = Object.keys(hydratedTerminals)[0] || '';
      setActiveTerminalId((current) => (current && hydratedTerminals[current] ? current : firstTerminalId));
      setSelected(Object.fromEntries((session.file_ids || []).map((fileId: string) => [fileId, true])));
      setEvents(normalizeEvents(session.activity_log || []));
      setPatchPreview(session.patch_preview || []);
      setPreviewChecks(session.preview_checks || []);
      if (session.preview_runtime?.preview_url && !previewUrl) setPreviewUrl(session.preview_runtime.preview_url);
      setAnalysis(session.workspace_analysis || null);
      setPatchReady(Boolean(session.patch_preview?.length || session.patch_text));
      const jobData = await apiRequest(`/api/v1/code/jobs?code_session_id=${encodeURIComponent(session.id)}`);
      setJobs(jobData);
      await refreshCommands(session.id);
      await refreshRuntimeStatus(session.id);
      await loadRollbackSnapshots(session.id);
      await refreshWorkspaceTasks(session.id);
      if (session.patch_preview?.length) {
        session.patch_preview.forEach((item: any) => {
          addEvent({
            kind: 'edit',
            message: `Pending change: ${item.filename}`,
            detail: `+${item.additions || 0} / -${item.deletions || 0}`,
            diff: item.diff,
          });
        });
      }
      try {
        const git = await apiRequest(`/api/v1/code/sessions/${session.id}/git/status`);
        if (git.git?.repo_url) setRepoUrl(git.git.repo_url);
        const gitMeta = git.git || {};
        if (gitMeta.repo_full_name) setSelectedGithubRepo(gitMeta.repo_full_name);
        if (gitMeta.working_branch) setGithubBranchName(gitMeta.working_branch);
      } catch {
        // Git metadata is optional for early workspaces.
      }
      await refreshGithubState();
      
      if (session.metadata_json?.local_workspace_path) {
        startFolderWatch(session.metadata_json.local_workspace_path);
      }
    } catch {
      localStorage.removeItem('nexus.code.session_id');
      setSessionId('');
      setLocalWorkspacePath('');
      setPatchPreview([]);
      setAnalysis(null);
      setRollbackSnapshots([]);
      setCommands([]);
      setRuntimeStatus(null);
      setDiagnostics([]);
      setTerminalSessions({});
      setActiveTerminalId('');
    }
  };

  const refreshDiagnostics = async (idValue: string) => {
    if (!idValue) {
      setDiagnostics([]);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/diagnostics`);
      setDiagnostics(data.diagnostics || []);
    } catch {
      setDiagnostics([]);
    }
  };

  const refreshJobs = async (idValue: string) => {
    if (!idValue) return;
    try {
      const jobData = await apiRequest(`/api/v1/code/jobs?code_session_id=${encodeURIComponent(idValue)}`);
      setJobs(jobData);
      const completedBackground = (jobData || []).find((job: AgentJob) => job.status === 'completed' && job.mode?.startsWith('background_') && Array.isArray(job.result?.patch_preview));
      if (completedBackground?.result?.patch_preview?.length) {
        setPatchPreview(completedBackground.result.patch_preview);
        setPatchReady(true);
      }
    } catch {
      setJobs([]);
    }
    try {
      const status = await apiRequest('/api/v1/code/worker/status');
      setWorkerStatus(status);
    } catch {
      setWorkerStatus({ enabled: false, alive: false });
    }
  };

  const refreshCurrentJobs = async () => {
    if (!sessionId) return;
    await refreshJobs(sessionId);
  };

  const cancelJob = async (jobId: string) => {
    if (busy) return;
    try {
      const job = await apiRequest(`/api/v1/code/jobs/${jobId}/cancel`, { method: 'POST' });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Job cancelled', detail: `${job.mode} - ${job.status}` });
    } catch (error) {
      reportWorkspaceError(error, 'Cancel job failed');
    }
  };

  const pauseJob = async (jobId: string) => {
    if (busy) return;
    try {
      const job = await apiRequest(`/api/v1/code/jobs/${jobId}/pause`, { method: 'POST' });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Job paused', detail: `${job.mode} - ${job.status}` });
    } catch (error) {
      reportWorkspaceError(error, 'Pause job failed');
    }
  };

  const resumeJob = async (jobId: string) => {
    if (busy) return;
    try {
      const job = await apiRequest(`/api/v1/code/jobs/${jobId}/resume`, { method: 'POST' });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 20));
      addEvent({ kind: 'code', message: 'Job resumed', detail: `${job.mode} - ${job.status}` });
    } catch (error) {
      reportWorkspaceError(error, 'Resume job failed');
    }
  };

  const retryJob = async (jobId: string) => {
    if (busy) return;
    try {
      const result = await apiRequest(`/api/v1/code/jobs/${jobId}/retry`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((item) => item.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'code', message: 'Background job retried', detail: result.job?.prompt || jobId });
    } catch (error) {
      reportWorkspaceError(error, 'Retry job failed');
    }
  };

  const upsertTerminal = (terminal?: TerminalSession | null) => {
    if (!terminal?.id) return;
    setTerminalSessions((current) => ({ ...current, [terminal.id]: terminal }));
    setActiveTerminalId(terminal.id);
  };

  const createLocalTerminal = async (shellProfile = 'powershell', options: { reuseExisting?: boolean } = {}) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.terminalCreate) {
      throw new Error('Open a folder first to create a trusted local terminal.');
    }
    if (options.reuseExisting !== false) {
      const existing = Object.values(terminalSessions).find((terminal) => terminal.id?.startsWith('local-') && sameLocalPath(terminal.cwd, trustedPath) && !['killed', 'exited', 'failed'].includes(terminal.status || ''));
      if (existing) {
        setActiveTerminalId(existing.id);
        return existing;
      }
    }
    const terminal = await electron.terminalCreate(trustedPath, { cols: 100, rows: 28, shell: shellProfile });
    const normalizedTerminal: TerminalSession = {
      id: terminal.id,
      status: terminal.status || 'active',
      cwd: terminal.cwd || trustedPath,
      backend: terminal.backend || 'unknown',
      history: terminal.history || [],
      logs: terminal.logs || [],
      created_at: terminal.created_at,
      updated_at: terminal.updated_at,
    };
    upsertTerminal(normalizedTerminal);
    addEvent({
      kind: terminal.backend === 'node-pty' ? 'deploy' : 'error',
      message: terminal.backend === 'node-pty' ? 'Local terminal created' : 'Local terminal fallback active',
      detail: terminal.backend === 'node-pty'
        ? (normalizedTerminal.cwd || trustedPath)
        : 'node-pty is unavailable, so Arceus is using command-bar mode. Run npm install in desktop or rebuild node-pty for full interactive terminal.',
    });
    return normalizedTerminal;
  };

  const createTerminal = async (shellProfile = 'powershell') => {
    if (busy) return;
    setTerminalPanelOpen(true);
    if (agentOnline === false) {
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
      if (!trustedPath || !electron?.terminalCreate) {
        addEvent({ kind: 'error', message: 'Open a folder for terminal', detail: 'The Agent API is offline. Local terminal still works after you open a trusted folder.' });
        return;
      }
    }
    try {
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
      if (trustedPath && electron?.terminalCreate) {
        await createLocalTerminal(shellProfile, { reuseExisting: false });
        return;
      }
      const sid = await ensureSession();
      const terminalId = id('cloud-terminal');
      const terminal: TerminalSession = {
        id: terminalId,
        status: 'connecting',
        cwd: 'cloud workspace',
        history: [],
        logs: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      upsertTerminal(terminal);
      addEvent({ kind: 'deploy', message: 'Cloud PTY terminal opening', detail: 'Connecting to agent-service WebSocket.' });
    } catch (error) {
      reportWorkspaceError(error, 'Terminal create failed', { chat: true, intent: 'Terminal' });
    }
  };

  const sendTerminalInput = async () => {
    const command = terminalCommand.trim();
    if (busy || !command) return;
    setTerminalPanelOpen(true);
    try {
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
      if (trustedPath && electron?.terminalInput) {
        const localTerminal = activeTerminalId?.startsWith('local-')
          ? terminalSessions[activeTerminalId]
          : await createLocalTerminal();
        const terminalId = localTerminal.id;
        const result = await electron.terminalInput(terminalId, command);
        setTerminalSessions((current) => {
          const existing = current[terminalId] || {
            id: terminalId,
            cwd: trustedPath,
            status: 'active',
            logs: [],
            history: [],
          };
          return {
            ...current,
            [terminalId]: {
              ...existing,
              status: result.status || 'active',
              backend: result.backend || existing.backend,
              history: result.history || [...(existing.history || []), command],
              updated_at: new Date().toISOString(),
            },
          };
        });
        setActiveTerminalId(terminalId);
        setTerminalCommand('');
        addEvent({ kind: 'deploy', message: `Local terminal: ${command}`, detail: trustedPath || 'trusted workspace' });
        return;
      }
      if (agentOnline === false) {
        addEvent({ kind: 'error', message: 'Open folder or start Agent API', detail: 'Local terminal needs a trusted folder. Cloud terminal needs agent-service on port 8003.' });
        return;
      }
      if (activeTerminalId?.startsWith('cloud-terminal') || activeTerminalId?.startsWith('pty-')) {
        setTerminalSessions((current) => {
          const existing = current[activeTerminalId];
          if (!existing) return current;
          return {
            ...current,
            [activeTerminalId]: {
              ...existing,
              logs: [
                ...(existing.logs || []),
                { status: 'input', output_excerpt: `${command}\r`, updated_at: new Date().toISOString(), source: 'cloud-pty' },
              ].slice(-240),
              history: [...(existing.history || []), command].slice(-80),
              updated_at: new Date().toISOString(),
            },
          };
        });
        setTerminalCommand('');
        addEvent({ kind: 'deploy', message: `Cloud terminal: ${command}`, detail: 'Command sent to active PTY.' });
        return;
      }
      const sid = await ensureSession();
      const result = activeTerminalId
        ? await apiRequest(`/api/v1/code/terminal/${activeTerminalId}/input`, {
            method: 'POST',
            body: JSON.stringify({ input: command }),
          })
        : await apiRequest(`/api/v1/code/sessions/${sid}/terminal`, {
            method: 'POST',
            body: JSON.stringify({ command, approved: false }),
          });
      upsertTerminal(result.terminal);
      if (result.job) setJobs((current) => [result.job, ...current.filter((item) => item.id !== result.job.id)].slice(0, 20));
      setTerminalCommand('');
      addEvent({
        kind: result.result?.status === 'failed' ? 'error' : 'deploy',
        message: `Terminal: ${command}`,
        detail: result.result?.output_excerpt || result.result?.status || 'Command recorded.',
      });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Terminal command failed', { chat: true, intent: 'Terminal' });
    }
  };

  const sendTerminalRawInput = useCallback(async (terminalId: string, input: string) => {
    if (!terminalId || !input || !terminalId.startsWith('local-')) return;
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.terminalInput) return;
    try {
      const result = await electron.terminalInput(terminalId, input, { raw: true });
      setTerminalSessions((current) => {
        const existing = current[terminalId];
        if (!existing) return current;
        return {
          ...current,
          [terminalId]: {
            ...existing,
            status: result.status || existing.status || 'active',
            backend: result.backend || existing.backend,
            history: result.history || existing.history || [],
            updated_at: new Date().toISOString(),
          },
        };
      });
    } catch (error) {
      reportWorkspaceError(error, 'Terminal input failed');
    }
  }, [activeProject?.local_workspace_path, activeProject?.metadata?.local_workspace_path, localWorkspacePath]);

  const resizeTerminal = useCallback(async (terminalId: string, cols: number, rows: number) => {
    if (!terminalId || !terminalId.startsWith('local-')) return;
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    if (!electron?.terminalResize) return;
    try {
      await electron.terminalResize(terminalId, cols, rows);
    } catch {
      // Resize is best-effort; stale terminals may disappear during reloads.
    }
  }, []);

  const handleCloudTerminalFrame = useCallback((terminalId: string, frame: Record<string, any>) => {
    if (!terminalId) return;
    const frameType = frame.type || frame.event || 'event';
    setTerminalSessions((current) => {
      const existing = current[terminalId];
      if (!existing) return current;
      const output = typeof frame.data === 'string'
        ? frame.data
        : frame.message || frame.reason || '';
      const nextStatus =
        frameType === 'ready' ? 'active'
          : frameType === 'exit' ? 'exited'
          : frameType === 'error' ? 'failed'
          : frameType === 'blocked' ? 'blocked'
          : frameType === 'connecting' ? 'connecting'
          : existing.status || 'active';
      return {
        ...current,
        [terminalId]: {
          ...existing,
          status: nextStatus,
          cwd: frame.cwd || existing.cwd,
          logs: output
            ? [
                ...(existing.logs || []),
                {
                  status: frameType,
                  output_excerpt: String(output),
                  updated_at: new Date().toISOString(),
                  source: 'cloud-pty',
                },
              ].slice(-240)
            : existing.logs || [],
          updated_at: new Date().toISOString(),
        },
      };
    });
  }, []);

  useEffect(() => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const hasLocalTerminal = Object.values(terminalSessions).some((terminal) => terminal.id?.startsWith('local-') && sameLocalPath(terminal.cwd, trustedLocalPath) && !['killed', 'exited', 'failed'].includes(terminal.status || ''));
    const autoKey = `${projectId || 'workspace'}:${trustedLocalPath}`;
    if (!terminalPanelOpen || !trustedLocalPath || hasLocalTerminal || busy || !electron?.terminalCreate || autoCreatedTerminalRef.current === autoKey) return;
    autoCreatedTerminalRef.current = autoKey;
    void createLocalTerminal('powershell', { reuseExisting: true }).catch((error) => {
      autoCreatedTerminalRef.current = '';
      addEvent({
        kind: 'error',
        message: 'Local terminal unavailable',
        detail: classifyError(error).hint,
      });
    });
  }, [busy, projectId, terminalPanelOpen, terminalSessions, trustedLocalPath]);

  useEffect(() => {
    if (!normalizedTrustedLocalPath || rightPanelOpen) return;
    setRightPanelView('explorer');
    setRightPanelOpen(true);
  }, [normalizedTrustedLocalPath, rightPanelOpen]);

  const killTerminal = async (terminalId: string) => {
    if (busy || !terminalId) return;
    try {
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      if (terminalId.startsWith('local-') && electron?.terminalKill) {
        const result = await electron.terminalKill(terminalId);
        setTerminalSessions((current) => ({
          ...current,
          [terminalId]: {
            ...(current[terminalId] || { id: terminalId, history: [], logs: [] }),
            status: result.status || 'killed',
            updated_at: new Date().toISOString(),
          },
        }));
        addEvent({ kind: 'done', message: 'Local terminal killed', detail: terminalId.slice(0, 8) });
        return;
      }
      if (terminalId.startsWith('cloud-terminal') || terminalId.startsWith('pty-')) {
        setTerminalSessions((current) => ({
          ...current,
          [terminalId]: {
            ...(current[terminalId] || { id: terminalId, history: [], logs: [] }),
            status: 'killed',
            logs: [
              ...((current[terminalId]?.logs || [])),
              {
                status: 'killed',
                output_excerpt: 'Terminal killed.',
                updated_at: new Date().toISOString(),
                source: 'cloud-pty',
              },
            ].slice(-240),
            updated_at: new Date().toISOString(),
          },
        }));
        addEvent({ kind: 'done', message: 'Cloud terminal killed', detail: terminalId.slice(0, 8) });
        return;
      }
      const result = await apiRequest(`/api/v1/code/terminal/${terminalId}/kill`, { method: 'POST' });
      upsertTerminal(result.terminal);
      addEvent({ kind: 'done', message: 'Terminal killed', detail: terminalId.slice(0, 8) });
    } catch (error) {
      reportWorkspaceError(error, 'Kill terminal failed');
    }
  };

  const clearTerminal = (terminalId: string) => {
    setTerminalSessions((current) => {
      const terminal = current[terminalId];
      if (!terminal) return current;
      return {
        ...current,
        [terminalId]: {
          ...terminal,
          logs: [],
          updated_at: new Date().toISOString(),
        },
      };
    });
  };

  const restartTerminal = async (terminalId: string) => {
    await killTerminal(terminalId);
    await createTerminal();
  };

  const refreshCommands = async (idValue: string) => {
    if (!idValue) {
      setCommands([]);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/commands`);
      setCommands(data.commands || []);
    } catch {
      setCommands([]);
    }
  };

  const refreshRuntimeStatus = async (idValue = sessionId) => {
    if (!idValue) {
      setRuntimeStatus(null);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/runtime/status`);
      setRuntimeStatus(data);
    } catch {
      setRuntimeStatus(null);
    }
  };

  const refreshGithubState = async () => {
    try {
      const status = await apiRequest('/api/v1/github/status');
      let repos = status.repositories || [];
      let staged = githubStatus?.staged;
      if (status.connected) {
        try {
          const repoResult = await apiRequest('/api/v1/github/repositories');
          repos = repoResult.repositories || repos;
        } catch {
          // Keep cached repositories from status if refresh fails.
        }
      }
      if (sessionId) {
        try {
          const stagedResult = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/staged`);
          staged = stagedResult.staged || staged;
        } catch {
          // Staged patch state should not block GitHub connection refresh.
        }
      }
      setGithubRepositories(repos);
      setGithubStatus((current) => ({
        ...(current || {}),
        ...status,
        repositories: repos,
        staged,
      }));
      if (!selectedGithubRepo && repos[0]?.full_name) setSelectedGithubRepo(repos[0].full_name);
    } catch {
      setGithubStatus(null);
      setGithubRepositories([]);
      setGithubBranches([]);
    }
  };

  const refreshGithubStagedState = async (idValue = sessionId) => {
    if (!idValue) return;
    try {
      const stagedResult = await apiRequest(`/api/v1/code/sessions/${idValue}/github/staged`);
      setGithubStatus((current) => ({
        ...(current || {}),
        staged: stagedResult.staged,
      }));
    } catch {
      // Keep the current Git state when staged metadata is unavailable.
    }
  };

  const refreshGithubBranches = async (repository = selectedGithubRepo, forceDefault = false) => {
    if (!repository) {
      setGithubBranches([]);
      return;
    }
    try {
      const result = await apiRequest(`/api/v1/github/branches?repository=${encodeURIComponent(repository)}`);
      const branches = result.branches || [];
      setGithubBranches(branches);
      setGithubBaseBranch((current) => (forceDefault ? branches[0]?.name || '' : current || branches[0]?.name || ''));
    } catch {
      setGithubBranches([]);
      setGithubBaseBranch('');
    }
  };

  useEffect(() => {
    refreshGithubBranches(selectedGithubRepo, true);
  }, [selectedGithubRepo]);

  useEffect(() => {
    const onGitHubConnected = (event: MessageEvent) => {
      if (event.data?.type !== 'arceus.github.connected') return;
      refreshGithubState();
      addEvent({ kind: 'done', message: 'GitHub connected', detail: 'Repository access is ready. Choose a repo to import or open a PR.' });
    };
    window.addEventListener('message', onGitHubConnected);
    return () => window.removeEventListener('message', onGitHubConnected);
  }, []);

  const loadRollbackSnapshots = async (idValue = sessionId) => {
    if (!idValue) {
      setRollbackSnapshots([]);
      return;
    }
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${idValue}/rollback-snapshots`);
      setRollbackSnapshots(data.snapshots || []);
    } catch {
      setRollbackSnapshots([]);
    }
  };

  useEffect(() => {
    try {
      const rawOpenProjects = localStorage.getItem(OPEN_PROJECTS_KEY);
      if (rawOpenProjects) {
        const parsed = JSON.parse(rawOpenProjects);
        if (Array.isArray(parsed)) setOpenProjectIds(parsed.filter(Boolean).slice(0, MAX_OPEN_PROJECTS));
      }
      const activeProjectId = localStorage.getItem(ACTIVE_PROJECT_KEY);
      if (activeProjectId) setProjectId(activeProjectId);
    } catch {
      // Project switcher state is optional.
    }
    loadProjects();
    loadFiles();
    const params = new URLSearchParams(window.location.search);
    const querySessionId = params.get('session_id');
    const savedSessionId = querySessionId || localStorage.getItem('nexus.code.session_id');
    if (savedSessionId) {
      if (querySessionId) {
        localStorage.setItem('nexus.code.session_id', querySessionId);
      }
      hydrateSession(savedSessionId);
    }
    const raw = sessionStorage.getItem('design_to_workspace');
    if (raw) {
      try {
        const payload = JSON.parse(raw);
        setMode('design');
        setPrompt(`Implement this selected ${payload.style} design as production-ready frontend code.\n\nBrief: ${payload.brief}\n\nDesign notes:\n${payload.notes}\n\nPreview code:\n${payload.code}`);
      } catch {
        sessionStorage.removeItem('design_to_workspace');
      }
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const hasRunningJob = jobs.some((job) => ['running', 'queued', 'claimed', 'retrying', 'cancel_requested'].includes(job.status));
    if (!hasRunningJob) return;
    const timer = window.setInterval(() => {
      void refreshJobs(sessionId);
    }, typeof window !== 'undefined' && typeof EventSource !== 'undefined' ? 10000 : 4000);
    return () => window.clearInterval(timer);
  }, [jobs, sessionId]);

  useEffect(() => {
    const streamableJobs = jobs.filter((job) => job.id && ['queued', 'claimed', 'running', 'retrying', 'cancel_requested'].includes(job.status || ''));
    if (!streamableJobs.length || typeof window === 'undefined' || typeof EventSource === 'undefined') return;
    const sources = streamableJobs.map((job) => {
      const source = new EventSource(`/api/v1/jobs/${job.id}/stream`);
      source.addEventListener('log', (event) => {
        try {
          const log = JSON.parse((event as MessageEvent).data);
          setJobs((current) => current.map((item) => (
            item.id === job.id
              ? { ...item, logs: [...(item.logs || []), log].slice(-300) }
              : item
          )));
        } catch {
          // The polling fallback will correct malformed stream data.
        }
      });
      source.addEventListener('status', (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data);
          setJobs((current) => current.map((item) => (
            item.id === job.id
              ? { ...item, status: payload.status || item.status, progress: payload.progress || item.progress }
              : item
          )));
        } catch {
          // Polling fallback remains active.
        }
      });
      source.addEventListener('done', (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data);
          setJobs((current) => [payload, ...current.filter((item) => item.id !== payload.id)].slice(0, 20));
        } catch {
          void refreshCurrentJobs();
        }
        source.close();
      });
      source.onerror = () => {
        source.close();
      };
      return source;
    });
    return () => sources.forEach((source) => source.close());
  }, [jobs.map((job) => `${job.id}:${job.status}`).join('|')]);

  useEffect(() => {
    if (!projectId || sessionId || busy || !projects.some((project) => project.id === projectId)) return;
    void openCodeProject(projectId);
  }, [busy, projectId, projects, sessionId]);

  useEffect(() => {
    const failedJob = jobs.find((job) => ['failed', 'timeout', 'dead_letter'].includes(job.status || ''));
    const previewIssue = previewChecks.find((check) => check.status && check.status !== 'passed');
    const activeTerminal = Object.values(terminalSessions).find((terminal) => ['running', 'active'].includes(terminal.status || '') && (terminal.logs || []).length > 0);
    if (activeTerminal && lastAutoOpenedTerminalRef.current !== activeTerminal.id) {
      lastAutoOpenedTerminalRef.current = activeTerminal.id;
      setTerminalPanelOpen(true);
    }
    if (rightPanelOpen) return;
    if (patchPreview.length > 0) {
      setRightPanelView('changes');
      setRightPanelOpen(true);
    } else if (failedJob) {
      setRightPanelView('jobs');
      setRightPanelOpen(true);
    } else if (previewIssue) {
      setRightPanelView('preview');
      setRightPanelOpen(true);
    }
  }, [jobs, patchPreview.length, previewChecks, rightPanelOpen, terminalPanelOpen, terminalSessions]);

  useEffect(() => {
    const value = prompt.trim();
    if (!value) {
      setBackendSuggestions([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void fetchBackendSuggestions(value, mode);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [mode, prompt, selectedFileIds.join('|'), openTabs.map((file) => file.id).join('|'), activeFileId, sessionId]);

  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).electron && sessionId) {
      const flushDirectorySync = async () => {
        if (directorySyncRunningRef.current) return;
        directorySyncRunningRef.current = true;
        directorySyncTimerRef.current = null;
        const queued = directorySyncQueueRef.current.splice(0);
        const latestByPath = new Map<string, any>();
        for (const item of queued) {
          if (!item?.path) continue;
          latestByPath.set(String(item.path), item);
        }
        const changes = Array.from(latestByPath.values());
        if (!changes.length) {
          directorySyncRunningRef.current = false;
          return;
        }
        try {
          let latestSession: any = null;
          const syncableChanges = changes.filter((item) => item.event !== 'addDir' && item.event !== 'unlinkDir').slice(0, 120);
          for (const item of syncableChanges) {
            latestSession = await apiRequest(`/api/v1/code/sessions/${sessionId}/sync-local-file`, {
              method: 'POST',
              body: JSON.stringify({
                action: item.event,
                relative_path: item.path,
              }),
            });
            if (latestSession?.status === 'skipped' && latestSession?.skipped) {
              const reason = latestSession.skipped.reason === 'file_too_large'
                ? `Skipped large file (${Math.ceil((latestSession.skipped.size_bytes || 0) / 1024)} KB): ${latestSession.skipped.relative_path}`
                : `Skipped ${latestSession.skipped.reason?.replace(/_/g, ' ') || 'unsupported file'}: ${latestSession.skipped.relative_path}`;
              addEvent({ kind: 'read', message: 'Local file skipped', detail: reason });
            }
          }
          if (latestSession?.file_ids) {
            setSelected(Object.fromEntries((latestSession.file_ids || []).map((fileId: string) => [fileId, true])));
          }
          await loadFiles();
          await refreshLocalTree();
          if (!latestSession && sessionId) await hydrateSession(sessionId);
          setFolderWatchError(null);
          addEvent({
            kind: 'done',
            message: 'Workspace synced',
            detail: changes.length === 1
              ? `${changes[0].event} file: ${changes[0].path}`
              : `${changes.length} local file changes synced from disk.`,
          });
        } catch (err) {
          addEvent({
            kind: 'error',
            message: 'Local folder sync skipped',
            detail: err instanceof Error ? err.message : 'A local file change could not be synced.',
          });
        } finally {
          directorySyncRunningRef.current = false;
          if (directorySyncQueueRef.current.length > 0 && directorySyncTimerRef.current === null) {
            directorySyncTimerRef.current = window.setTimeout(flushDirectorySync, 250);
          }
        }
      };

      const unsubscribe = (window as any).electron.onDirectoryChanged((change: any) => {
        const changes = Array.isArray(change?.changes) ? change.changes : [change].filter(Boolean);
        if (!changes.length) return;
        directorySyncQueueRef.current.push(...changes);
        if (directorySyncTimerRef.current !== null) {
          window.clearTimeout(directorySyncTimerRef.current);
        }
        directorySyncTimerRef.current = window.setTimeout(flushDirectorySync, 250);
      });
      return () => {
        if (directorySyncTimerRef.current !== null) {
          window.clearTimeout(directorySyncTimerRef.current);
          directorySyncTimerRef.current = null;
        }
        directorySyncQueueRef.current = [];
        unsubscribe();
      };
    }
  }, [refreshLocalTree, sessionId]);

  const uploadFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    setBusy(true);
    try {
      const nextSelected = { ...selected };
      for (const file of Array.from(fileList)) {
        const isZip = file.name.toLowerCase().endsWith('.zip');
        addEvent({
          kind: 'read',
          message: `${isZip ? 'Importing project' : 'Uploading'} ${file.name}`,
          detail: isZip ? 'Extracting supported code files into this workspace.' : 'Extracting text and adding it to workspace context.',
        });
        const formData = new FormData();
        formData.append('upload', file);
        if (isZip) {
          const sid = await ensureSession();
          const result = await apiRequest(`/api/v1/code/sessions/${sid}/import-zip`, { method: 'POST', body: formData });
          (result.imported || []).forEach((item: any) => {
            nextSelected[item.id] = true;
          });
          if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
          addEvent({ kind: 'done', message: 'Project archive imported', detail: `${result.imported?.length || 0} files imported, ${result.skipped || 0} skipped.` });
        } else {
          const uploaded = await apiRequest('/api/v1/files?owner_type=code_workspace', { method: 'POST', body: formData });
          nextSelected[uploaded.id] = true;
        }
      }
      setSelected(nextSelected);
      await loadFiles();
      if (sessionId) {
        const fileIds = Object.entries(nextSelected).filter(([, value]) => value).map(([fileId]) => fileId);
        await apiRequest(`/api/v1/code/sessions/${sessionId}/files`, {
          method: 'PATCH',
          body: JSON.stringify({ file_ids: fileIds }),
        });
        await refreshCommands(sessionId);
        await loadProjects();
      }
      addEvent({ kind: 'done', message: 'Files ready', detail: 'Uploaded files can now be used by hidden agents.' });
    } catch (error) {
      reportWorkspaceError(error, 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const ensureSession = async () => {
    if (sessionId) {
      await apiRequest(`/api/v1/code/sessions/${sessionId}/files`, {
        method: 'PATCH',
        body: JSON.stringify({ file_ids: selectedFileIds }),
      });
      return sessionId;
    }
    const session = projectId
      ? await apiRequest(`/api/v1/code/projects/${projectId}/sessions`, {
        method: 'POST',
        body: JSON.stringify({ title: `${activeProject?.name || 'Arceus Code'} chat`, file_ids: selectedFileIds, project_id: projectId }),
      })
      : await apiRequest('/api/v1/code/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: 'Arceus Code unified workspace', file_ids: selectedFileIds, project_id: projectId || undefined }),
    });
    setSessionId(session.id);
    localStorage.setItem('nexus.code.session_id', session.id);
    addEvent({ kind: 'start', message: 'Code session created', detail: session.id });
    await refreshJobs(session.id);
    await refreshCommands(session.id);
    return session.id;
  };

  const openWorkspaceFile = async (file: WorkspaceFile) => {
    if (busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/files/${file.id}/content`);
      let content = data.content || '';
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      if (localWorkspacePath && electron?.readFile) {
        try {
          const nativeFile = await electron.readFile(localWorkspacePath, data.filename);
          content = nativeFile.content || content;
        } catch {
          // API content remains the safe fallback for cloud/app-managed files.
        }
      }
      const nextFile = { id: data.id, filename: data.filename, content, dirty: false };
      setOpenTabs((current) => {
        const exists = current.some((item) => item.id === nextFile.id);
        return exists ? current.map((item) => item.id === nextFile.id ? { ...nextFile, dirty: item.dirty, content: item.dirty ? item.content : nextFile.content } : item) : [...current, nextFile];
      });
      setActiveFileId(nextFile.id);
      addEvent({ kind: 'read', message: `Opened ${data.filename}`, detail: 'Loaded into the inline editor.' });
    } catch (error) {
      reportWorkspaceError(error, 'Open file failed');
    } finally {
      setBusy(false);
    }
  };

  const openDiagnosticFile = async (diagnostic: WorkspaceDiagnostic) => {
    const diagnosticFile = String(diagnostic.file || '').replace(/\\/g, '/').toLowerCase();
    if (!diagnosticFile || diagnosticFile === 'unknown') return;
    const target = files.find((file) => {
      const filename = file.filename.replace(/\\/g, '/').toLowerCase();
      return filename.endsWith(diagnosticFile) || diagnosticFile.endsWith(filename) || filename.endsWith(diagnosticFile.split('/').pop() || '');
    });
    if (target) await openWorkspaceFile(target);
  };

  const openReceiptFile = async (filename: string) => {
    const query = filename.replace(/\\/g, '/').toLowerCase();
    if (!query) return;
    const basename = query.split('/').pop() || query;
    const target = files.find((file) => {
      const candidate = file.filename.replace(/\\/g, '/').toLowerCase();
      return candidate === query || candidate.endsWith(`/${query}`) || query.endsWith(`/${candidate}`) || candidate.endsWith(`/${basename}`);
    });
    if (target) {
      await openWorkspaceFile(target);
      return;
    }
    setFilesOpen(true);
    setSearchQuery(filename);
    addEvent({ kind: 'read', message: 'File lookup prepared', detail: `Search opened for ${filename}.` });
  };

  const searchWorkspace = async () => {
    const query = searchQuery.trim();
    if (!query || busy) return;
    setFilesOpen(true);
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/search?q=${encodeURIComponent(query)}`);
      setSearchMatches(result.matches || []);
      const summary = result.summary || {};
      const breakdown = [
        summary.symbols ? `${summary.symbols} symbol` : '',
        summary.files ? `${summary.files} file` : '',
        summary.dependencies ? `${summary.dependencies} import` : '',
        summary.routes ? `${summary.routes} route` : '',
        summary.text ? `${summary.text} text` : '',
      ].filter(Boolean).join(' · ');
      addEvent({
        kind: 'read',
        message: 'Workspace search complete',
        detail: `${result.matches?.length || 0} match(es) for "${query}"${breakdown ? ` · ${breakdown}` : ''}.`,
      });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Workspace search failed');
    } finally {
      setBusy(false);
    }
  };

  const saveOpenFile = async () => {
    if (!openFile || busy) return;
    setBusy(true);
    try {
      const electron = typeof window !== 'undefined' ? (window as any).electron : null;
      let nativeWrite: { size_bytes?: number } | null = null;
      if (localWorkspacePath && electron?.writeFile) {
        nativeWrite = await electron.writeFile(localWorkspacePath, openFile.filename, openFile.content);
      }
      const result = await apiRequest(`/api/v1/files/${openFile.id}/content`, {
        method: 'PUT',
        body: JSON.stringify({ content: openFile.content }),
      });
      updateOpenTab(openFile.id, (file) => ({ ...file, dirty: false }));
      addEvent({
        kind: 'done',
        message: `Saved ${result.filename}`,
        detail: nativeWrite
          ? `${nativeWrite.size_bytes ?? result.size_bytes} bytes written to trusted local folder and workspace storage.`
          : `${result.size_bytes} bytes written to workspace storage.`,
      });
      await loadFiles();
      await refreshLocalTree();
      if (sessionId) {
        await hydrateSession(sessionId);
      }
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Save failed');
    } finally {
      setBusy(false);
      if (autoCompile) {
        void runChecks({ ignoreBusy: true, reason: 'Auto-Compile is enabled, so Arceus is verifying the applied patch.' });
      }
    }
  };

  const syncLocalFileReference = async (action: 'add' | 'change' | 'unlink', relativePath: string) => {
    if (!sessionId || !relativePath) return;
    const updatedSession = await apiRequest(`/api/v1/code/sessions/${sessionId}/sync-local-file`, {
      method: 'POST',
      body: JSON.stringify({ action, relative_path: relativePath }),
    });
    if (updatedSession?.status === 'skipped') {
      addEvent({
        kind: 'read',
        message: 'Local file skipped',
        detail: updatedSession.skipped?.reason === 'file_too_large'
          ? `${relativePath} is larger than the inline workspace limit. It remains on disk but is not loaded into chat context.`
          : `${relativePath} could not be loaded into chat context.`,
      });
      await loadFiles();
      await refreshLocalTree();
      return;
    }
    setSelected(Object.fromEntries((updatedSession.file_ids || []).map((fileId: string) => [fileId, true])));
    await loadFiles();
    await refreshLocalTree();
    await hydrateSession(updatedSession.id || sessionId);
  };

  const createLocalWorkspaceItem = async (type: 'file' | 'folder', basePath = '') => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.createItem) {
      addEvent({ kind: 'error', message: 'Open a folder first', detail: 'Local file creation works inside a trusted Electron folder.' });
      return;
    }
    const defaultName = type === 'folder' ? 'new-folder' : 'new-file.txt';
    const suggested = basePath ? `${basePath.replace(/\\/g, '/').replace(/\/$/, '')}/${defaultName}` : defaultName;
    const relativePath = suggested.trim().replace(/\\/g, '/');
    if (!relativePath) return;
    setBusy(true);
    try {
      const result = await electron.createItem(trustedPath, relativePath, type, type === 'file' ? '' : undefined);
      if (type === 'file') await syncLocalFileReference('add', result.path || relativePath);
      else {
        await refreshLocalTree(trustedPath);
        if (sessionId) await hydrateSession(sessionId);
      }
      addEvent({ kind: 'done', message: `${type === 'folder' ? 'Folder' : 'File'} created`, detail: result.path || relativePath });
    } catch (error) {
      reportWorkspaceError(error, `Create ${type} failed`);
    } finally {
      setBusy(false);
    }
  };

  const renameLocalWorkspaceFile = async (file: WorkspaceFile, providedNextPath?: string) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.renameItem) {
      addEvent({ kind: 'error', message: 'Open a folder first', detail: 'Local rename works inside a trusted Electron folder.' });
      return;
    }
    if (!providedNextPath) {
      addEvent({ kind: 'error', message: 'Rename needs a target path', detail: 'Use the file tree rename action so Arceus can avoid unsupported browser prompts.' });
      return;
    }
    const nextPath = providedNextPath.trim().replace(/\\/g, '/');
    if (!nextPath || nextPath === file.filename) return;
    setBusy(true);
    try {
      const result = await electron.renameItem(trustedPath, file.filename, nextPath);
      await syncLocalFileReference('unlink', file.filename);
      await syncLocalFileReference('add', result.to || nextPath);
      setOpenTabs((current) => current.map((tab) => tab.id === file.id ? { ...tab, filename: result.to || nextPath } : tab));
      addEvent({ kind: 'done', message: 'File renamed', detail: `${file.filename} -> ${result.to || nextPath}` });
    } catch (error) {
      reportWorkspaceError(error, 'Rename failed');
    } finally {
      setBusy(false);
    }
  };

  const deleteLocalWorkspaceFile = async (file: WorkspaceFile) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.deleteItem) {
      addEvent({ kind: 'error', message: 'Open a folder first', detail: 'Local delete works inside a trusted Electron folder.' });
      return;
    }
    if (!window.confirm(`Delete ${file.filename} from the trusted folder? This changes the local filesystem.`)) return;
    setBusy(true);
    try {
      await electron.deleteItem(trustedPath, file.filename);
      await syncLocalFileReference('unlink', file.filename);
      setOpenTabs((current) => current.filter((tab) => tab.id !== file.id));
      if (activeFileId === file.id) setActiveFileId('');
      addEvent({ kind: 'done', message: 'File deleted', detail: file.filename });
    } catch (error) {
      reportWorkspaceError(error, 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  const revealLocalWorkspacePath = async (relativePath: string) => {
    const electron = typeof window !== 'undefined' ? (window as any).electron : null;
    const trustedPath = localWorkspacePath || activeProject?.local_workspace_path || activeProject?.metadata?.local_workspace_path || '';
    if (!trustedPath || !electron?.revealItem) return;
    try {
      await electron.revealItem(trustedPath, relativePath);
    } catch (error) {
      reportWorkspaceError(error, 'Reveal failed');
    }
  };

  const inlineEditSelection = async (instruction: string, selectedText: string, start: number, end: number) => {
    if (!openFile || busy) return;
    if (!selectedText.trim()) {
      addEvent({ kind: 'error', message: 'Inline edit needs a selection', detail: 'Select the code you want Arceus to rewrite.' });
      return;
    }
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'edit', message: `Inline editing ${openFile.filename}`, detail: instruction });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/inline-edit`, {
        method: 'POST',
        body: JSON.stringify({
          file_id: openFile.id,
          filename: openFile.filename,
          instruction,
          selected_text: selectedText,
          full_content: openFile.content,
          ...model,
        }),
      });
      const replacement = result.replacement || '';
      updateOpenTab(openFile.id, (file) => ({
        ...file,
        content: `${file.content.slice(0, start)}${replacement}${file.content.slice(end)}`,
        dirty: true,
      }));
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'edit', message: 'Inline edit applied to editor', detail: 'Review the replacement, then save the file if it looks right.' });
    } catch (error) {
      reportWorkspaceError(error, 'Inline edit failed', { chat: true, intent: 'Inline edit' });
    } finally {
      setBusy(false);
    }
  };

  const completeAtCursor = async (cursor: number) => {
    if (!openFile || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const prefix = openFile.content.slice(0, cursor);
      const suffix = openFile.content.slice(cursor);
      addEvent({ kind: 'edit', message: `Completing ${openFile.filename}`, detail: 'Generating a short insertion at the cursor.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/complete`, {
        method: 'POST',
        body: JSON.stringify({
          file_id: openFile.id,
          filename: openFile.filename,
          prefix,
          suffix,
          ...model,
        }),
      });
      const completion = result.completion || '';
      updateOpenTab(openFile.id, (file) => ({
        ...file,
        content: `${file.content.slice(0, cursor)}${completion}${file.content.slice(cursor)}`,
        dirty: true,
      }));
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'edit', message: 'Completion inserted into editor', detail: 'Review the insertion, then save the file if it looks right.' });
    } catch (error) {
      reportWorkspaceError(error, 'Completion failed');
    } finally {
      setBusy(false);
    }
  };

  const fetchActivityPlan = async (value: string, currentMode: WorkspaceMode) => {
    try {
      const headers = await createApiHeadersAsync();
      const response = await fetch(`/api/v1/code/activity-stream?prompt=${encodeURIComponent(value)}&mode=${currentMode}`, { headers });
      const text = await response.text();
      text.split('\n\n').forEach((chunk) => {
        const line = chunk.split('\n').find((part) => part.startsWith('data: '));
        if (!line) return;
        try {
          const parsed = JSON.parse(line.slice(6));
          addEvent({ kind: parsed.kind || 'start', message: parsed.message, detail: parsed.detail });
        } catch {
          // Ignore malformed activity chunks.
        }
      });
    } catch {
      addEvent({ kind: 'start', message: 'Local orchestrator active', detail: 'Backend activity stream unavailable; continuing with local activity.' });
    }
  };

  const compileMissionPreview = async (instruction: string): Promise<CompiledMissionPreview | null> => {
    if (!autoCompile) return null;
    const projectRef = projectId || activeProject?.id || 'local-workspace';
    try {
      const compiled = await apiRequest('/api/v1/os/missions/compile', {
        method: 'POST',
        body: JSON.stringify({
          tenant_id: 'default',
          project_id: projectRef,
          objective: instruction,
          repository_ids: repoUrl ? [repoUrl] : [],
          constraints: trustedLocalPath ? [`Trusted local workspace: ${trustedLocalPath}`] : [],
          desired_outcomes: [],
          budget: { currency: 'USD', maximum: 10 },
        }),
      });
      setMissionPreview(compiled);
      addEvent({
        kind: compiled.state === 'CLARIFICATION_REQUIRED' ? 'error' : 'code',
        message: compiled.state === 'CLARIFICATION_REQUIRED' ? 'Mission needs clarification' : 'Mission compiled',
        detail: compiled.definition?.title || instruction,
      });
      return compiled;
    } catch (error) {
      const classified = classifyError(error);
      addEvent({
        kind: 'error',
        message: classified.message || 'Mission compile failed',
        detail: classified.hint || 'The request can still continue through the existing workspace flow.',
      });
      return null;
    }
  };

  const approveMissionPlanPath = () => {
    if (!missionPreview) return;
    addEvent({
      kind: 'code',
      message: 'Mission plan path approved',
      detail: missionPreview.definition?.title || 'Arceus can continue with the compiled mission path.',
    });
  };

  const runWorkspace = async (customPrompt?: string) => {
    const instruction = typeof customPrompt === 'string' ? customPrompt.trim() : prompt.trim();
    if (!instruction || busy) return;
    if (agentOnline === false) {
      addEvent({ kind: 'error', message: 'Agent API offline', detail: 'Restart Electron after Docker Postgres/Redis are healthy, or start agent-service on port 8003.' });
      addMessage('user', instruction);
      addMessage('assistant', 'The local agent API is offline. Start or restart Arceus Electron so the backend service on port 8003 is running, then try again.');
      return;
    }
    const activeTask = workspaceTasks.find((task) => task.id === typedSuggestionId);
    const activeTaskMetadata = activeTask?.metadata || {};
    const activeTaskAcceptance = Array.isArray(activeTaskMetadata.acceptance_criteria) ? activeTaskMetadata.acceptance_criteria : [];
    const activeTaskContext = activeTask
      ? `\n\nSelected Arceus task:\n- Title: ${activeTask.title}\n- Mode: ${activeTask.mode}\n- Risk: ${activeTask.risk || 'medium'}\n- Approval required: ${activeTask.requiresApproval ? 'yes' : 'no'}\n- Expected files: ${(activeTask.files || []).join(', ') || 'infer from workspace'}\n- Planned steps: ${(activeTask.steps || []).join(' | ') || 'inspect, plan, execute safely'}\n- Expected commands: ${(activeTask.expectedCommands || activeTask.commands || []).join(', ') || 'recommend checks'}\n- Orchestration source: ${activeTaskMetadata.source || 'workspace'}\n- Orchestration task id: ${activeTaskMetadata.orchestration_task_id || 'none'}\n- Assigned role: ${activeTaskMetadata.assigned_role || 'agent'}\n- Acceptance criteria: ${activeTaskAcceptance.join(' | ') || 'use the task summary'}`
      : '';
    const agentInstruction = `${instruction}${activeTaskContext}`;
    const effectiveFileIds = resolveEffectiveFileIds(instruction);
    const autoBoundActiveFile = Boolean(openFile?.id && effectiveFileIds.includes(openFile.id) && !selectedFileIds.includes(openFile.id));
    setBusy(true);
    setPatchReady(false);
    const nextActionSnapshot = suggestions.slice(0, 3);
    addMessage('user', instruction);
    setPrompt('');
    setBackendSuggestions([]);
    const compiledMission = await compileMissionPreview(instruction);
    if (compiledMission?.state === 'CLARIFICATION_REQUIRED') {
      const questions = compiledMission.definition?.unknowns || compiledMission.intent?.unknowns || [];
      addMessage(
        'assistant',
        `I compiled this into a mission, but execution is blocked until these questions are answered:\n\n${questions.map((item) => `- ${item}`).join('\n') || '- Clarify the high-risk unknowns before execution.'}`
      );
      setBusy(false);
      return;
    }
    if (activeTask?.id) {
      try {
        const accepted = await apiRequest(`/api/v1/code/tasks/${activeTask.id}/accept`, { method: 'POST' });
        const normalized = normalizeWorkspaceSuggestion(accepted);
        setWorkspaceTasks((current) => [normalized, ...current.filter((task) => task.id !== normalized.id)].slice(0, 20));
        addEvent({ kind: 'code', message: `Accepted task: ${normalized.title}`, detail: normalized.summary });
      } catch {
        addEvent({ kind: 'code', message: `Accepted task: ${activeTask.title}`, detail: 'Task persistence unavailable; continuing locally.' });
      }
    }
    await fetchActivityPlan(instruction, mode);
    const modes = inferModes(instruction, mode);
    const outputs: string[] = [];
    let planText = '';
    let currentPreview: any[] = [];
    let latestBackendPayload: any = null;
    const checksSummary: Array<{ label: string; status?: string }> = [];
    const commandSummary: Array<{ label: string; status?: string }> = [];
    let producedPatch = false;
    let reviewRequiredAfterPatch = false;

    try {
      if (autoBoundActiveFile && openFile) {
        addEvent({ kind: 'read', message: `Using active file: ${openFile.filename}`, detail: 'The prompt points at the current file, so Arceus included it as context.' });
      } else if (effectiveFileIds.length) {
        addEvent({ kind: 'read', message: `Reading ${effectiveFileIds.length} selected file${effectiveFileIds.length === 1 ? '' : 's'}`, detail: 'File context is injected into every hidden agent call.' });
      }

      if (modes.includes('research')) {
        addEvent({ kind: 'research', message: 'Research agent running', detail: 'Gathering relevant web context.' });
        const result = await apiRequest('/api/v1/internet/research', {
          method: 'POST',
          body: JSON.stringify({ query: agentInstruction, depth: 'standard' }),
        });
        outputs.push(result.report || JSON.stringify(result, null, 2));
        addEvent({ kind: 'done', message: 'Research complete' });
      }

      if (modes.includes('design')) {
        addEvent({ kind: 'design', message: 'Design agent running', detail: 'Generating implementation-ready UI guidance.' });
        const result = await apiRequest('/api/v1/design/generate-ui', {
          method: 'POST',
          body: JSON.stringify({ description: agentInstruction, output_type: 'ui', ...model }),
        });
        outputs.push(result.content || JSON.stringify(result, null, 2));
        addEvent({ kind: 'done', message: 'Design generated' });
      }

      if (modes.includes('deploy')) {
        addEvent({ kind: 'deploy', message: 'Deploy agent analyzing', detail: 'No production deploy is triggered without explicit approval.' });
        const result = await apiRequest('/api/v1/deploy/analyze', {
          method: 'POST',
          body: JSON.stringify({ project_type: 'Arceus Code workspace', repo_context: agentInstruction }),
        });
        outputs.push(`Deployment analysis:\n${JSON.stringify(result, null, 2)}`);
        addEvent({ kind: 'done', message: 'Deploy analysis ready' });
      }

      if (modes.includes('code') || modes.includes('plan')) {
        const sid = await ensureSession();
        addEvent({ kind: 'code', message: 'Planning code changes', detail: 'Generating a concise implementation plan.' });
        const plan = await apiRequest(`/api/v1/code/sessions/${sid}/plan`, {
          method: 'POST',
          body: JSON.stringify({ instruction: agentInstruction, file_ids: effectiveFileIds, ...model }),
        });
        latestBackendPayload = plan;
        if (plan.job) setJobs((current) => [plan.job, ...current.filter((job) => job.id !== plan.job.id)].slice(0, 20));
        planText = plan.plan || '';
        outputs.push(`Implementation plan:\n${plan.plan}`);
        if (modes.includes('code')) {
          addEvent({ kind: 'edit', message: 'Preparing changes', detail: 'Safe file changes apply automatically; risky changes stay in review.' });
          const patch = await apiRequest(`/api/v1/code/sessions/${sid}/patch`, {
            method: 'POST',
            body: JSON.stringify({ instruction: agentInstruction, file_ids: effectiveFileIds, ...model }),
          });
          latestBackendPayload = patch;
          if (patch.job) setJobs((current) => [patch.job, ...current.filter((job) => job.id !== patch.job.id)].slice(0, 20));
          const preview = patch.patch_preview || [];
          currentPreview = preview;
          setPatchPreview(preview);
          setPatchReady(true);
          producedPatch = true;
          if (preview.length) {
            preview.forEach((item: any) => {
              addEvent({
                kind: 'edit',
                message: `Prepared ${item.operation || 'modify'}: ${item.new_filename || item.filename}`,
                detail: `+${item.additions || 0} / -${item.deletions || 0}`,
                diff: item.diff,
              });
            });
          } else {
            addEvent({ kind: 'edit', message: 'Patch prepared', detail: summarizePatch(patch.patch), diff: patch.patch });
          }
          try {
            const safeApply: SafeApplyResult = await apiRequest(`/api/v1/code/sessions/${sid}/apply-safe`, { method: 'POST' });
            latestBackendPayload = safeApply;
            if (safeApply.job) setJobs((current) => [safeApply.job!, ...current.filter((job) => job.id !== safeApply.job!.id)].slice(0, 20));
            const changed = safeApply.changed || [];
            const remaining = safeApply.remaining || [];
            const impact = safeApply.impact || {};
            reviewRequiredAfterPatch = Boolean(remaining.length);
            currentPreview = changed.length ? changed : remaining;
            setPatchPreview(remaining);
            setPatchReady(Boolean(remaining.length));
            if (changed.length) {
              addEvent({
                kind: 'done',
                message: 'Changes applied',
                detail: `${changed.length} safe change${changed.length === 1 ? '' : 's'} applied. Undo is available.`,
              });
              changed.forEach((item: any) => {
                addEvent({
                  kind: 'edit',
                  message: `Applied ${item.new_filename || item.filename}`,
                  detail: `${item.operation || 'modify'} · +${item.additions || 0} / -${item.deletions || 0}`,
                  diff: item.diff,
                });
              });
              outputs.push(
                `Applied ${changed.length} safe change${changed.length === 1 ? '' : 's'} automatically. Undo is available.\n` +
                `+${impact.total_additions || 0} / -${impact.total_deletions || 0}` +
                (remaining.length ? `\n\n${remaining.length} review-required change${remaining.length === 1 ? '' : 's'} remain in Changes.` : '')
              );
              await loadFiles();
              await hydrateSession(sid);
              await loadRollbackSnapshots(sid);
              await refreshGithubStagedState(sid);
            } else {
              outputs.push(`Review required before applying changes.\n\n${summarizePreview(remaining.length ? remaining : preview)}`);
            }
            if (remaining.length) {
              addEvent({
                kind: 'edit',
                message: 'Review required',
                detail: `${remaining.length} risky or conflicted change${remaining.length === 1 ? '' : 's'} need manual review.`,
              });
              setRightPanelView('changes');
              setRightPanelOpen(true);
            }
          } catch (error) {
            const classified = classifyError(error);
            addEvent({
              kind: 'error',
              message: classified.message || 'Auto-apply failed',
              detail: classified.hint || 'Open Changes to review the pending patch.',
            });
            outputs.push(`Changes prepared but not applied automatically.\n\n${summarizePreview(preview)}`);
          }
        }
      }

      commandSummary.push(...jobs.slice(0, 3).flatMap((job) => (job.commands_run || []).map((command: any) => ({
        label: typeof command === 'string' ? command : command.command || job.prompt || job.mode,
        status: typeof command === 'string' ? 'recorded' : command.status || job.status,
      }))));
      if (!commandSummary.length) {
        commandSummary.push(...commands.slice(0, 4).map((command) => ({ label: command.command || command.label, status: 'recommended' })));
      }
      if (producedPatch && reviewRequiredAfterPatch) checksSummary.push({ label: 'Review remaining changes', status: 'pending' });
      const fallbackReceipt = buildReceipt({
        summary: producedPatch ? `Applied ${currentPreview.length || 1} workspace change${currentPreview.length === 1 ? '' : 's'}.` : 'Workspace request completed.',
        receiptMode: modes.length > 1 ? 'mixed' : modes[0],
        intent: modes.map((item) => item[0].toUpperCase() + item.slice(1)).join(' + '),
        plan: planText,
        preview: currentPreview,
        commandsRun: commandSummary,
        checks: checksSummary,
        approvalState: producedPatch ? (reviewRequiredAfterPatch ? 'applied with review required' : 'applied') : 'done',
        nextActions: nextActionSnapshot,
        contextFileIds: effectiveFileIds,
      });
      const receipt = buildWorkReceiptFromPayload(
        latestBackendPayload || { work_receipt: currentPreview.length ? { files_changed: currentPreview } : undefined },
        fallbackReceipt
      );
      addMessage('assistant', outputs.join('\n\n---\n\n') || 'Done.', receipt);
      addEvent({ kind: 'done', message: 'Arceus Code finished', detail: modes.join(', ') });
      if (activeTask?.id) {
        try {
          const nextStatus = producedPatch ? 'waiting_approval' : 'done';
          const updated = await apiRequest(`/api/v1/code/tasks/${activeTask.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: nextStatus }),
          });
          const normalized = normalizeWorkspaceSuggestion(updated);
          setWorkspaceTasks((current) => [normalized, ...current.filter((task) => task.id !== normalized.id)].slice(0, 20));
        } catch {
          // Task status is best-effort; the agent result remains visible in chat/activity.
        }
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 402) {
        setUpgradePrompt(error.detail || { message: error.message });
      }
      const classified = reportWorkspaceError(error, 'Workspace run failed');
      addMessage(
        'assistant',
        `${classified.message}\n\n${classified.hint}${classified.raw ? `\n\nDetails: ${classified.raw}` : ''}`,
        {
          ...buildErrorReceipt(classified, inferReceiptIntent(instruction)),
          nextActions: nextActionSnapshot,
        }
      );
      if (activeTask?.id) {
        try {
          const updated = await apiRequest(`/api/v1/code/tasks/${activeTask.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'failed' }),
          });
          const normalized = normalizeWorkspaceSuggestion(updated);
          setWorkspaceTasks((current) => [normalized, ...current.filter((task) => task.id !== normalized.id)].slice(0, 20));
        } catch {
          // Task status is best-effort.
        }
      }
    } finally {
      setBusy(false);
      setTypedSuggestionId('');
    }
  };

  const runWorkspaceBackground = async () => {
    const instruction = prompt.trim();
    if (!instruction || busy) return;
    const effectiveFileIds = resolveEffectiveFileIds(instruction);
    setBusy(true);
    setPatchReady(false);
    addMessage('user', instruction);
    setPrompt('');
    try {
      const sid = await ensureSession();
      const modes = inferModes(instruction, mode);
      const backgroundMode = modes.includes('code') ? 'code' : 'plan';
      addEvent({ kind: 'code', message: 'Background job queued', detail: `${backgroundMode}: ${instruction}` });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/run-background`, {
        method: 'POST',
        body: JSON.stringify({ instruction, mode: backgroundMode, file_ids: effectiveFileIds, ...model }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addMessage('assistant', `Background ${backgroundMode} job started. Track it in the Jobs drawer; pending patches will appear in Changes when ready.`);
    } catch (error) {
      const classified = reportWorkspaceError(error, 'Background job failed to start');
      addMessage('assistant', `${classified.message}\n\n${classified.hint}`, buildErrorReceipt(classified, 'Background job'));
    } finally {
      setBusy(false);
    }
  };

  const confirmPatchConflicts = async (): Promise<{ ok: boolean; allowConflicts: boolean }> => {
    if (!sessionId) return { ok: true, allowConflicts: false };
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/check-conflicts`);
      if (Array.isArray(result.patch_preview)) {
        setPatchPreview(result.patch_preview);
      }
      const conflicts = result.conflicts || [];
      if (!conflicts.length) return { ok: true, allowConflicts: false };
      const names = conflicts.slice(0, 4).map((item: any) => item.filename).join(', ');
      addEvent({
        kind: 'error',
        message: 'Patch conflict detected',
        detail: `${conflicts.length} file(s) changed after the patch was generated: ${names}`,
      });
      const allowConflicts = window.confirm(`Patch conflict detected in ${conflicts.length} file(s): ${names}\n\nApply anyway?`);
      return { ok: allowConflicts, allowConflicts };
    } catch {
      return { ok: true, allowConflicts: false };
    }
  };

  const applyChanges = async () => {
    if (!sessionId || !patchReady || busy) return;
    const conflictDecision = await confirmPatchConflicts();
    if (!conflictDecision.ok) return;
    setBusy(true);
    try {
      addEvent({ kind: 'edit', message: 'Applying approved patch', detail: 'Writing changes into app-managed workspace files.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ allow_conflicts: conflictDecision.allowConflicts }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setPatchPreview(result.remaining || []);
      const changed = result.changed || [];
      const impact = result.impact || {};
      const impactText = [
        `${impact.created_files?.length || 0} created`,
        `${impact.modified_files?.length || 0} modified`,
        `${impact.deleted_files?.length || 0} deleted`,
        `${impact.renamed_files?.length || 0} renamed`,
        `${impact.folders_created?.length || 0} folders`,
        `+${impact.total_additions || 0} / -${impact.total_deletions || 0}`,
      ].join(' · ');
      changed.forEach((item: any) => {
        addEvent({ kind: 'edit', message: `Edited ${item.filename}`, detail: `${item.diff?.split('\n').length || 0} diff lines`, diff: item.diff });
      });
      setPatchReady(false);
      addMessage(
        'assistant',
        `Applied ${changed.length} approved item${changed.length === 1 ? '' : 's'}.\n${impactText}\n${result.summary || ''}`.trim(),
        buildWorkReceiptFromPayload(
          result,
          buildReceipt({
            summary: `Applied ${changed.length} approved change${changed.length === 1 ? '' : 's'}.`,
            receiptMode: 'code',
            intent: 'Apply',
            preview: changed,
            checks: autoCompile ? [{ label: 'Auto-compile checks', status: 'queued' }] : [],
            approvalState: 'approved',
            nextActions: suggestions.slice(0, 3),
          })
        )
      );
      await loadFiles();
      if (sessionId) {
        await hydrateSession(sessionId);
        await loadRollbackSnapshots(sessionId);
        await refreshGithubStagedState(sessionId);
      }
    } catch (error) {
      reportWorkspaceError(error, 'Apply failed', { chat: true, intent: 'Patch apply' });
    } finally {
      setBusy(false);
      if (autoCompile) {
        runChecks();
      }
    }
  };

  const applyPatchSelection = async (selection: { fileIds?: string[]; operationIds?: string[]; hunkIds?: string[] }) => {
    if (!sessionId || busy) return;
    const conflictDecision = await confirmPatchConflicts();
    if (!conflictDecision.ok) return;
    setBusy(true);
    let applied = false;
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, {
        method: 'POST',
        body: JSON.stringify({
          file_ids: selection.fileIds || [],
          operation_ids: selection.operationIds || [],
          hunk_ids: selection.hunkIds || [],
          allow_conflicts: conflictDecision.allowConflicts,
        }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      const remaining = result.remaining || [];
      setPatchPreview(remaining);
      setPatchReady(Boolean(remaining.length));
      const impact = result.impact || {};
      (result.changed || []).forEach((item: any) => {
        addEvent({ kind: 'edit', message: `Applied ${item.filename}`, detail: `${item.diff?.split('\n').length || 0} diff lines`, diff: item.diff });
      });
      addMessage(
        'assistant',
        `Applied selected review item${(result.changed || []).length === 1 ? '' : 's'}: ${(result.changed || []).length}. +${impact.total_additions || 0} / -${impact.total_deletions || 0}.`,
        buildWorkReceiptFromPayload(
          result,
          buildReceipt({
            summary: `Applied ${(result.changed || []).length} selected change${(result.changed || []).length === 1 ? '' : 's'}.`,
            receiptMode: 'code',
            intent: 'Apply selection',
            preview: result.changed || [],
            approvalState: remaining.length ? 'partially approved' : 'approved',
            nextActions: suggestions.slice(0, 3),
          })
        )
      );
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
      await refreshGithubStagedState(sessionId);
      await refreshGithubStagedState(sessionId);
      applied = true;
    } catch (error) {
      reportWorkspaceError(error, 'Apply selection failed', { chat: true, intent: 'Patch apply' });
    } finally {
      setBusy(false);
      if (applied && autoCompile) {
        void runChecks({ ignoreBusy: true, reason: 'Auto-Compile is enabled, so Arceus is verifying the applied file.' });
      }
    }
  };

  const rejectPatchSelection = async (selection: { fileIds?: string[]; operationIds?: string[] }) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/reject`, {
        method: 'POST',
        body: JSON.stringify({
          file_ids: selection.fileIds || [],
          operation_ids: selection.operationIds || [],
        }),
      });
      const remaining = result.remaining || [];
      setPatchPreview(remaining);
      setPatchReady(Boolean(remaining.length));
      addEvent({ kind: 'done', message: 'Patch selection rejected', detail: `${result.rejected?.length || 0} operation(s) removed from review.` });
    } catch (error) {
      reportWorkspaceError(error, 'Reject selection failed');
    } finally {
      setBusy(false);
    }
  };

  const updateHunkReview = async (hunkId: string, action: 'approve' | 'reject') => {
    if (!sessionId || busy) return;
    try {
      await apiRequest(`/api/v1/code/sessions/${sessionId}/hunks/${encodeURIComponent(hunkId)}/${action}`, { method: 'POST' });
      const preview = await apiRequest(`/api/v1/code/sessions/${sessionId}/patch-preview`);
      setPatchPreview(preview.patch_preview || []);
      addEvent({ kind: 'edit', message: `${action === 'approve' ? 'Accepted' : 'Rejected'} hunk`, detail: hunkId });
    } catch (error) {
      reportWorkspaceError(error, 'Hunk review failed');
    }
  };

  const resetPatchReview = async () => {
    if (!sessionId || busy) return;
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/hunks/reset`, { method: 'POST' });
      setPatchPreview(result.patch_preview || []);
      addEvent({ kind: 'edit', message: 'Patch review reset', detail: 'All hunks are pending again.' });
    } catch (error) {
      reportWorkspaceError(error, 'Reset review failed');
    }
  };

  const runCommand = async (command: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: `Running ${command}`, detail: 'Executing in an isolated temporary workspace from selected files.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/runtime/command`, {
        method: 'POST',
        body: JSON.stringify({ command, timeout_seconds: 60 }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: result.status === 'passed' ? 'done' : 'error',
        message: `${command} ${result.status}`,
        detail: result.output,
      });
      await hydrateSession(sid);
      await refreshRuntimeStatus(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Command failed', { chat: true, intent: 'Command' });
    } finally {
      setBusy(false);
    }
  };

  const runChecks = async (options: { ignoreBusy?: boolean; reason?: string } = {}) => {
    if (busy && !options.ignoreBusy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: 'Running workspace checks', detail: options.reason || 'Arceus will run detected safe build/test/lint/typecheck commands.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/run-checks`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: result.status === 'passed' ? 'done' : 'error',
        message: `Workspace checks ${result.status}`,
        detail: `${result.passed || 0}/${result.total || 0} check(s) passed.`,
      });
      await hydrateSession(sid);
      await refreshRuntimeStatus(sid);
      await refreshDiagnostics(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Workspace checks failed', { chat: true, intent: 'Checks' });
    } finally {
      setBusy(false);
    }
  };

  const syncRuntime = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/runtime/sync`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: 'done',
        message: 'Runtime workspace synced',
        detail: `${result.files_written?.length || 0} file(s) written. Runtime is ready for safe commands.`,
      });
      await hydrateSession(sid);
      await refreshRuntimeStatus(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Runtime sync failed');
    } finally {
      setBusy(false);
    }
  };

  const installRuntime = async () => {
    if (busy) return;
    const approved = window.confirm('Install dependencies inside the isolated runtime? This can download packages and may take a few minutes.');
    if (!approved) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: 'Installing dependencies', detail: 'Running an approved install command inside the runtime sandbox.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/runtime/install`, {
        method: 'POST',
        body: JSON.stringify({ approved: true, timeout_seconds: 300 }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: result.status === 'passed' ? 'done' : 'error',
        message: `Install ${result.status}`,
        detail: result.output_excerpt || result.output || '',
      });
      await hydrateSession(sid);
      await refreshRuntimeStatus(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Install failed', { chat: true, intent: 'Install' });
    } finally {
      setBusy(false);
    }
  };

  const analyzeWorkspace = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'read', message: 'Analyzing workspace', detail: 'Indexing imports, symbols, routes, dependencies, entrypoints, and hotspots.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/analyze`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setAnalysis(result);
      addEvent({
        kind: 'done',
        message: 'Workspace analysis complete',
        detail: `${result.summary?.files || 0} file(s), ${result.summary?.total_lines || 0} line(s), ${result.imports?.length || 0} import(s), ${result.symbols?.length || 0} symbol(s).`,
      });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Workspace analysis failed');
    } finally {
      setBusy(false);
    }
  };

  const checkPreview = async () => {
    const url = previewUrl.trim();
    if (!url || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: 'Checking preview', detail: url });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/preview-check`, {
        method: 'POST',
        body: JSON.stringify({ url }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      const detail = [
        result.status_code ? `HTTP ${result.status_code}` : '',
        result.title ? `Title: ${result.title}` : '',
        result.issues?.length ? `Issues: ${result.issues.join(', ')}` : '',
        result.screenshot_base64 || result.screenshot_url ? 'Screenshot captured' : '',
        result.console_errors?.length ? `${result.console_errors.length} console error(s)` : '',
        result.network_failures?.length ? `${result.network_failures.length} network failure(s)` : '',
        result.blank_page ? 'Blank page detected' : '',
      ].filter(Boolean).join('\n');
      addEvent({ kind: result.status === 'passed' ? 'done' : 'error', message: `Preview check ${result.status}`, detail });
      setPreviewChecks((current) => [...current, result].slice(-30));
      addMessage(
        'assistant',
        result.status === 'passed'
          ? 'Preview verification passed. Screenshot and browser evidence are available in Preview.'
          : 'Preview verification found an issue. Open Preview for screenshot, console, and network evidence, or type the fix action below.',
        buildPreviewReceipt(result, activeProject?.name || 'Workspace')
      );
      setRightPanelView('preview');
      setRightPanelOpen(true);
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Preview check failed', { chat: true, intent: 'Preview' });
    } finally {
      setBusy(false);
    }
  };

  const startLivePreview = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: 'Starting live preview', detail: 'Using the persistent runtime workspace.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/preview/start`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      if (result.preview_url) setPreviewUrl(result.preview_url);
      if (result.status === 'running' || result.status === 'failed') {
        try {
          const logs = await apiRequest(`/api/v1/code/sessions/${sid}/preview/logs`);
          setPreviewLogs(logs);
        } catch {
          setPreviewLogs(null);
        }
      }
      addEvent({
        kind: result.status === 'running' ? 'done' : 'deploy',
        message: `Live preview ${result.status}`,
        detail: result.command || result.preview_url || 'Preview process started.',
      });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Live preview failed');
    } finally {
      setBusy(false);
    }
  };

  const stopLivePreview = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/preview/stop`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Live preview stopped', detail: result.command || '' });
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Stop preview failed');
    } finally {
      setBusy(false);
    }
  };

  const loadPreviewLogs = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const logs = await apiRequest(`/api/v1/code/sessions/${sessionId}/preview/logs`);
      setPreviewLogs(logs);
      addEvent({
        kind: logs.issues?.length ? 'error' : 'done',
        message: 'Preview logs loaded',
        detail: logs.issues?.length ? `Issues: ${logs.issues.join(', ')}` : 'No common error markers detected in recent logs.',
      });
    } catch (error) {
      reportWorkspaceError(error, 'Preview logs unavailable');
    } finally {
      setBusy(false);
    }
  };

  const fixPreviewIssue = async (instruction?: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      addEvent({ kind: 'edit', message: 'Fixing preview issue', detail: 'Using the latest preview check to prepare a patch.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/fix-preview`, {
        method: 'POST',
        body: JSON.stringify({ instruction: instruction || 'Prepare the smallest safe code change that fixes the preview failure.', ...model }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      const preview = result.patch_preview || [];
      setPatchPreview(preview);
      setPatchReady(Boolean(preview.length || result.patch));
      preview.forEach((item: any) => {
        addEvent({
          kind: 'edit',
          message: `Preview fix patch: ${item.filename}`,
          detail: `+${item.additions || 0} / -${item.deletions || 0}`,
          diff: item.diff,
        });
      });
      addMessage('assistant', `Preview fix prepared. Open Changes to review and approve.\n\n${summarizePreview(preview)}`);
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Fix preview failed', { chat: true, intent: 'Preview fix' });
    } finally {
      setBusy(false);
    }
  };

  const connectRepo = async () => {
    const url = repoUrl.trim();
    if (!url || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/git/connect`, {
        method: 'POST',
        body: JSON.stringify({ repo_url: url, default_branch: 'main' }),
      });
      addEvent({ kind: 'done', message: 'Repository connected', detail: `${result.repo_url} (${result.default_branch})` });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Repository connect failed');
    } finally {
      setBusy(false);
    }
  };

  const connectGithubApp = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await apiRequest('/api/v1/github/install-url');
      if (result.install_url) {
        window.open(result.install_url, '_blank', 'noopener,noreferrer');
      }
      addEvent({ kind: 'deploy', message: 'GitHub install opened', detail: 'Finish installation in GitHub, then refresh GitHub here.' });
    } catch (error) {
      reportWorkspaceError(error, 'GitHub connect failed');
    } finally {
      setBusy(false);
    }
  };

  const importGithubAppRepo = async () => {
    const repository = selectedGithubRepo.trim();
    if (!repository || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'read', message: 'Importing GitHub repository', detail: repository });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/github/import`, {
        method: 'POST',
        body: JSON.stringify({ repository, branch: githubBaseBranch || undefined }),
      });
      (result.imported || []).forEach((item: any) => {
        setSelected((current) => ({ ...current, [item.id]: true }));
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      if (result.git?.repo_url) setRepoUrl(result.git.repo_url);
      addEvent({ kind: 'done', message: 'GitHub repository imported', detail: `${result.imported?.length || 0} files imported, ${result.skipped || 0} skipped.` });
      await loadFiles();
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'GitHub import failed', { chat: true, intent: 'GitHub import' });
    } finally {
      setBusy(false);
    }
  };

  const importRepo = async () => {
    if (selectedGithubRepo) {
      await importGithubAppRepo();
      return;
    }
    const url = repoUrl.trim();
    if (!url || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'read', message: 'Importing GitHub repository', detail: url });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/git/import`, {
        method: 'POST',
        body: JSON.stringify({ repo_url: url }),
      });
      (result.imported || []).forEach((item: any) => {
        setSelected((current) => ({ ...current, [item.id]: true }));
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'GitHub repository imported', detail: `${result.imported?.length || 0} files imported, ${result.skipped || 0} skipped.` });
      await loadFiles();
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'GitHub import failed');
    } finally {
      setBusy(false);
    }
  };

  const createGithubBranch = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/branch`, {
        method: 'POST',
        body: JSON.stringify({ branch_name: githubBranchName || undefined, base_branch: githubBaseBranch || undefined }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setGithubBranchName(result.branch_name || githubBranchName);
      setGithubStatus((current) => ({ ...(current || {}), working_branch: result.branch_name, selected_repo: result.repo_full_name }));
      addEvent({ kind: 'done', message: 'GitHub branch ready', detail: `${result.branch_name} from ${result.base_branch}` });
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Create branch failed');
    } finally {
      setBusy(false);
    }
  };

  const preparePr = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/git/prepare-pr`, {
        method: 'POST',
        body: JSON.stringify({ title: 'Arceus Code workspace changes' }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: 'done',
        message: 'Pull request plan prepared',
        detail: `Branch: ${result.branch_name}\nCommit: ${result.commit_message}\n\n${result.pr_body}`,
      });
      await hydrateSession(sid);
    } catch (error) {
      reportWorkspaceError(error, 'Prepare PR failed');
    } finally {
      setBusy(false);
    }
  };

  const openPr = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      addEvent({ kind: 'deploy', message: 'Opening GitHub pull request', detail: 'Creating branch, committing files, and opening PR via GitHub API.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/git/open-pr`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: 'done',
        message: 'GitHub pull request opened',
        detail: `${result.pull_request_url}\n${result.committed?.length || 0} file(s) committed to ${result.branch_name}.`,
      });
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Open PR failed', { chat: true, intent: 'GitHub PR' });
    } finally {
      setBusy(false);
    }
  };

  const commitGithubChanges = async (message?: string, filenames?: string[]) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/commit`, {
        method: 'POST',
        body: JSON.stringify({ message: message || 'Arceus Code workspace changes', filenames }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setGithubStatus((current) => ({ ...(current || {}), selected_repo: result.repo_full_name, working_branch: result.branch_name, latest_commit_sha: result.commit_sha, staged: result.staged || current?.staged }));
      addEvent({ kind: 'done', message: 'GitHub commit created', detail: `${result.committed?.length || 0} file(s) committed to ${result.branch_name}.` });
      await hydrateSession(sessionId);
      await refreshGithubStagedState(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Commit failed', { chat: true, intent: 'GitHub commit' });
    } finally {
      setBusy(false);
    }
  };

  const openGithubAppPr = async (title?: string, body?: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/pr`, {
        method: 'POST',
        body: JSON.stringify({ title: title || 'Arceus Code workspace changes', body }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setGithubStatus((current) => ({ ...(current || {}), selected_repo: result.repo_full_name, working_branch: result.head_branch, pull_request_url: result.pull_request_url }));
      addEvent({ kind: 'done', message: 'GitHub pull request opened', detail: result.pull_request_url || '' });
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Open PR failed', { chat: true, intent: 'GitHub PR' });
    } finally {
      setBusy(false);
    }
  };

  const checkGithubPrStatus = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/pr-status`);
      setGithubStatus((current) => ({
        ...(current || {}),
        selected_repo: result.repo_full_name,
        latest_commit_sha: result.latest_commit_sha,
        pull_request_url: result.pull_request?.pull_request_url,
        checks: result.checks || [],
        check_summary: result.check_summary,
        staged: result.staged || current?.staged,
      }));
      addEvent({ kind: 'done', message: 'GitHub PR status refreshed', detail: `${result.checks?.length || 0} check run(s).` });
    } catch (error) {
      reportWorkspaceError(error, 'PR status failed');
    } finally {
      setBusy(false);
    }
  };

  const rejectChanges = async () => {
    if (sessionId) {
      try {
        await apiRequest(`/api/v1/code/sessions/${sessionId}/reject`, { method: 'POST' });
        await hydrateSession(sessionId);
      } catch {
        reportWorkspaceError(new Error('Pending patch could not be cleared on the server.'), 'Reject failed');
      }
    }
    setPatchReady(false);
    setPatchPreview([]);
    addEvent({ kind: 'done', message: 'Changes rejected', detail: 'Prepared patch was discarded from the UI approval flow.' });
  };

  const rollbackChanges = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/rollback`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Rolled back last apply', detail: `${result.restored?.length || 0} file(s) restored.` });
      addMessage(
        'assistant',
        `Rolled back ${result.restored?.length || 0} item${result.restored?.length === 1 ? '' : 's'}.`,
        buildWorkReceiptFromPayload(
          result,
          buildReceipt({
            summary: `Rolled back ${result.restored?.length || 0} item${result.restored?.length === 1 ? '' : 's'}.`,
            receiptMode: 'code',
            intent: 'Rollback',
            preview: result.restored || [],
            approvalState: 'restored',
            nextActions: suggestions.slice(0, 3),
          })
        )
      );
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
      await refreshGithubStagedState(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Rollback failed', { chat: true, intent: 'Rollback' });
    } finally {
      setBusy(false);
    }
  };

  const rollbackSnapshot = async (snapshotId: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/rollback`, {
        method: 'POST',
        body: JSON.stringify({ snapshot_id: snapshotId }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Rollback snapshot restored', detail: `${result.restored?.length || 0} file(s) restored.` });
      addMessage(
        'assistant',
        `Restored rollback snapshot ${result.snapshot?.snapshot_id ? result.snapshot.snapshot_id.slice(0, 8) : ''}. ${result.restored?.length || 0} item${result.restored?.length === 1 ? '' : 's'} restored.`,
        buildWorkReceiptFromPayload(
          result,
          buildReceipt({
            summary: `Restored ${result.restored?.length || 0} rollback item${result.restored?.length === 1 ? '' : 's'}.`,
            receiptMode: 'code',
            intent: 'Rollback',
            preview: result.restored || [],
            approvalState: 'restored',
            nextActions: suggestions.slice(0, 3),
          })
        )
      );
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Rollback snapshot failed', { chat: true, intent: 'Rollback' });
    } finally {
      setBusy(false);
    }
  };

  const commitAndOpenGithubPr = async (payload: { commit_message?: string; title?: string; body?: string; branch_name?: string; filenames?: string[] }) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/github/commit-pr`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setGithubStatus((current) => ({
        ...(current || {}),
        selected_repo: result.repo_full_name,
        working_branch: result.branch_name,
        latest_commit_sha: result.latest_commit_sha,
        pull_request_url: result.pull_request_url,
        checks: result.checks || [],
        check_summary: result.check_summary,
        staged: result.staged || current?.staged,
      }));
      addEvent({ kind: 'done', message: 'GitHub Commit -> PR completed', detail: result.pull_request_url || '' });
      await hydrateSession(sessionId);
    } catch (error) {
      reportWorkspaceError(error, 'Commit -> PR failed', { chat: true, intent: 'GitHub PR' });
    } finally {
      setBusy(false);
    }
  };

  const commandActions = useMemo<WorkspaceCommandAction[]>(() => {
    const failedJob = jobs.find((job) => ['failed', 'timeout', 'interrupted'].includes(job.status || ''));
    const currentFilename = openFile?.filename || 'current file';
    const previewFailed = previewChecks.some((check) => check.status !== 'passed');
    const hasGit = Boolean(githubStatus?.connected || repoUrl);
    return [
      {
        id: 'open-pending-changes',
        title: 'Open pending changes',
        detail: patchPreview.length ? `${patchPreview.length} file(s), +${patchPreview.reduce((total, item) => total + (item.additions || 0), 0)} / -${patchPreview.reduce((total, item) => total + (item.deletions || 0), 0)}` : 'No pending patch right now.',
        keywords: 'open pending changes review diff approval patch',
        rank: patchPreview.length ? 100 : 22,
        run: () => {
          setRightPanelOpen(true);
          setRightPanelView('changes');
        },
      },
      {
        id: 'fix-failing-build',
        title: 'Fix failing build',
        detail: failedJob ? failedJob.prompt || 'Use latest failed job output.' : 'No failed job detected; prepare a verification-first fix prompt.',
        keywords: 'fix failing build error failed job test lint typecheck',
        rank: failedJob ? 96 : 42,
        run: () => {
          setMode('code');
          setPrompt(failedJob ? `Fix the latest failed workspace job: ${failedJob.prompt || failedJob.mode}. Inspect the failure, identify root cause, prepare a small patch, and recommend checks.` : 'Check the workspace for build/test/lint failures, explain the root cause, and prepare the smallest safe fix.');
        },
      },
      {
        id: 'fix-preview-issue',
        title: 'Fix preview issue',
        detail: previewFailed ? 'Use latest preview evidence.' : 'Run a preview check first if needed.',
        keywords: 'fix preview issue browser screenshot console network',
        rank: previewFailed ? 90 : 45,
        run: () => {
          if (previewFailed) void fixPreviewIssue();
          else {
            setMode('code');
            setPrompt('Check the preview state, identify visible/runtime issues, and prepare the smallest fix plan before patching.');
          }
        },
      },
      {
        id: 'run-checks',
        title: 'Run checks',
        detail: commands.length ? commands.slice(0, 3).map((item) => item.command).join(', ') : 'Use detected safe build/test/lint commands.',
        keywords: 'run checks build test lint typecheck',
        rank: commands.length ? 84 : 60,
        run: () => runChecks({ reason: 'Started from command palette.' }),
      },
      {
        id: 'explain-current-file',
        title: 'Explain current file',
        detail: openFile ? currentFilename : 'Open a file first for the best explanation.',
        keywords: 'explain current file understand code',
        rank: openFile ? 82 : 25,
        run: () => {
          setMode('plan');
          setPrompt(`Explain ${currentFilename} in plain engineering language. Cover what it does, important functions/components, dependencies, risks, and where to modify it safely.`);
        },
      },
      {
        id: 'refactor-selected-code',
        title: 'Refactor selected code',
        detail: openFile ? `Prepare a reviewable refactor for ${currentFilename}.` : 'Open a file before refactoring.',
        keywords: 'refactor selected code clean simplify maintainability',
        rank: openFile ? 78 : 20,
        run: () => {
          setMode('code');
          setPrompt(`Refactor ${currentFilename} with the smallest reviewable change. Preserve behavior, explain files changed, line impact, and checks to run.`);
        },
      },
      {
        id: 'continue-last-task',
        title: 'Continue last task',
        detail: workspaceTasks[0]?.title || 'No durable task yet.',
        keywords: 'continue last task resume suggested task',
        rank: workspaceTasks.length ? 76 : 18,
        run: () => {
          const task = workspaceTasks[0];
          if (task) void typeSuggestion(task);
        },
      },
      {
        id: 'generate-tests',
        title: 'Generate tests',
        detail: openFile ? `Add or improve tests around ${currentFilename}.` : 'Find likely test targets from the workspace.',
        keywords: 'generate tests unit integration coverage',
        rank: openFile ? 74 : 58,
        run: () => {
          setMode('code');
          setPrompt(`Generate focused tests for ${openFile ? currentFilename : 'the current workspace task'}. Identify the code under test, add minimal test files, and recommend the exact test command.`);
        },
      },
      {
        id: 'create-pr',
        title: hasGit ? 'Create PR' : 'Connect GitHub',
        detail: hasGit ? 'Prepare branch, commit approved changes, and open PR.' : 'Install/connect GitHub before PR automation.',
        keywords: 'github git pr pull request branch commit connect',
        rank: hasGit && patchPreview.length ? 72 : 55,
        run: () => {
          setRightPanelOpen(true);
          setRightPanelView('git');
          if (hasGit) void preparePr();
          else void connectGithubApp();
        },
      },
      {
        id: 'connect-apps',
        title: 'Open app connectors',
        detail: 'GitHub, runtime CLI, preview, deploy, browser, and future connectors.',
        keywords: 'apps connectors integrations github runtime cli preview deploy browser',
        rank: 52,
        run: () => {
          setRightPanelOpen(true);
          setRightPanelView('apps');
        },
      },
    ].sort((a, b) => b.rank - a.rank);
  }, [commands, githubStatus, jobs, openFile, patchPreview, previewChecks, repoUrl, workspaceTasks]);

  const visibleCommandActions = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return commandActions
      .filter((action) => !query || `${action.title} ${action.detail} ${action.keywords}`.toLowerCase().includes(query))
      .slice(0, 7);
  }, [commandActions, searchQuery]);

  const runCommandAction = (action: WorkspaceCommandAction) => {
    setCommandPaletteOpen(false);
    setSearchQuery('');
    void action.run();
  };

  return (
    <DesktopOnlyGuard product="Arceus Code" reason="Arceus Code is optimized for desktop workspaces with files, editor, terminal-style actions, preview, diffs, jobs, and Git controls.">
      <main className={styles.workspace}>
      <WorkspaceSidebar
        recentItems={recentItems}
        busy={busy}
        onCreateProject={createProject}
        onNewChat={newChat}
        onSearch={focusWorkspaceSearch}
        onOpenRecent={openRecent}
        onImportLocal={importLocalDirectory}
        onToggleFiles={() => openRightTool('explorer')}
        onToggleEditor={() => setEditorOpen(!editorOpen)}
        editorOpen={editorOpen}
        activeProjectId={projectId}
        mergeSelection={mergeSelection}
        onToggleMergeProject={toggleMergeProject}
        onMergeSelectedProjects={mergeSelectedProjects}
        onCloseProject={closeProjectTab}
        onRemoveProject={removeProjectFromApp}
      />
      <header className={styles.topbar}>
        <div className={styles.breadcrumb}>
          <span>Arceus Code</span>
          <strong>{activeProject?.name || 'Workspace'}</strong>
        </div>
        {openProjects.length > 0 && (
          <div className={styles.projectTabs} aria-label="Open projects">
            {openProjects.map((project) => (
              <button
                key={project.id}
                type="button"
                className={project.id === projectId ? styles.projectTabActive : styles.projectTab}
                onClick={() => void openCodeProject(project.id)}
                title={project.local_workspace_path || project.name}
              >
                <span>{project.name}</span>
                <em>{project.file_count ?? project.file_ids?.length ?? 0}</em>
              </button>
            ))}
          </div>
        )}
        <div
          className={styles.commandSearchWrap}
          onBlur={() => window.setTimeout(() => setCommandPaletteOpen(false), 120)}
        >
          <input
            className={styles.search}
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value);
              setCommandPaletteOpen(true);
            }}
            onFocus={() => {
              setCommandPaletteOpen(true);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                const firstAction = visibleCommandActions[0];
                if (firstAction) runCommandAction(firstAction);
                else searchWorkspace();
              }
              if (event.key === 'Escape') setCommandPaletteOpen(false);
            }}
            placeholder="Search files, commands, agents..."
          />
          {commandPaletteOpen && (
            <div className={styles.commandPalette}>
              <div className={styles.commandPaletteHeader}>
                <span>Recommended actions</span>
                <em>{searchQuery.trim() ? 'filtered' : 'ranked by workspace state'}</em>
              </div>
              {visibleCommandActions.map((action) => (
                <button key={action.id} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => runCommandAction(action)}>
                  <strong>{action.title}</strong>
                  <span>{action.detail}</span>
                </button>
              ))}
              <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={searchWorkspace}>
                <strong>Search workspace files</strong>
                <span>{searchQuery.trim() ? `Find "${searchQuery.trim()}" in files, symbols, imports, and routes.` : 'Type a query to search files and code intelligence.'}</span>
              </button>
            </div>
          )}
        </div>
        <div className={styles.topActions}>
          <span className={styles.projectBadge} title={`Sandbox: ${sandboxType}`}>
            <Circle size={7} fill="currentColor" /> {agentOnline === false ? 'API offline' : runtimeStatus?.status || 'ready'}
          </span>
          
          <div className={styles.settingsWrapper}>
            <button 
              className={styles.settingsGearBtn} 
              type="button" 
              onClick={() => setSettingsOpen(!settingsOpen)}
              title="Workspace Settings"
            >
              <Settings size={15} />
            </button>
            {settingsOpen && (
              <div className={styles.settingsPopover}>
                <h4>Workspace Configuration</h4>
                <div className={styles.settingItem}>
                  <label>
                    <input 
                      type="checkbox" 
                      checked={autoCompile} 
                      onChange={(e) => setAutoCompile(e.target.checked)} 
                    />
                    <span>Auto-Compile Code</span>
                  </label>
                </div>
                <div className={styles.settingItem}>
                  <label>
                    <input 
                      type="checkbox" 
                      checked={autoRunCommands} 
                      onChange={(e) => setAutoRunCommands(e.target.checked)} 
                    />
                    <span>Auto-Run Agent Commands</span>
                  </label>
                </div>
                <div className={styles.settingItem}>
                  <label>Sandbox</label>
                  <select 
                    value={sandboxType} 
                    onChange={(e) => setSandboxType(e.target.value)}
                  >
                    <option value="local">Local Sandbox</option>
                    <option value="docker">Docker Container</option>
                    <option value="e2b">E2B Cloud</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          <button className={styles.iconButton} type="button" title="More workspace actions">
            <MoreHorizontal size={15} />
          </button>
          <UserCircle size={18} />
        </div>
      </header>
      <div className={styles.serviceRecoverySlot}>
        <ServiceRecoveryBanner
          health={serviceHealth}
          compact
          onRetry={refreshServiceHealth}
          onOpenTerminal={() => setTerminalPanelOpen(true)}
          onOpenDiagnostics={() => {
            setRightPanelOpen(true);
            setRightPanelView('jobs');
          }}
        />
      </div>
      <div className={styles.layout}>
        <div className={`${styles.workspaceBody} ${!editorOpen ? styles.layoutNoEditor : ''} ${!rightPanelOpen ? styles.layoutRightCollapsed : ''}`}>
          {editorOpen && (
          <EditorPanel
            file={openFile}
            tabs={openTabs}
            activeFileId={activeFileId}
            busy={busy}
            onChange={(content) => {
              if (openFile) updateOpenTab(openFile.id, (file) => ({ ...file, content, dirty: true }));
            }}
            onSave={saveOpenFile}
            onSelectTab={setActiveFileId}
            onCloseTab={closeOpenTab}
            onInlineEdit={inlineEditSelection}
            onComplete={completeAtCursor}
            onToggleExpand={() => setEditorOpen(false)}
            isCollapsed={false}
            diagnostics={diagnostics}
            onOpenDiagnostic={openDiagnosticFile}
            onDiagnosticsChange={setDiagnostics}
            workspaceRoot={trustedLocalPath}
          />
        )}
          <ConversationPanel
          mode={mode}
          messages={messages}
          prompt={prompt}
          busy={busy}
          selectedFileCount={selectedFileIds.length}
          suggestions={suggestions}
          missionPreview={missionPreview}
          activeProjectName={activeProject?.name || ''}
          activeSessionLabel={sessionId ? `session ${sessionId.slice(0, 8)}` : ''}
          onModeChange={setMode}
          onPromptChange={updatePrompt}
          onTypeSuggestion={typeSuggestion}
          onSubmit={runWorkspace}
          onSubmitBackground={runWorkspaceBackground}
          onAttachClick={() => fileInputRef.current?.click()}
          onClearMissionPreview={() => setMissionPreview(null)}
          onApproveMissionPlan={approveMissionPlanPath}
            onOpenTool={(tool) => {
              if (tool === 'terminal') {
                setTerminalPanelOpen(true);
                return;
              }
              setRightPanelView(tool);
              setRightPanelOpen(true);
            }}
            onOpenFile={openReceiptFile}
            onRollback={rollbackChanges}
          />
        {rightPanelOpen && rightPanelView === 'explorer' && (
          <div className={styles.rightExplorerPanel}>
            <div className={styles.rightDrawerHeader}>
              <span>Folder Structure</span>
              <button type="button" onClick={() => setRightPanelOpen(false)}>Close</button>
            </div>
            <FileExplorer
              files={visibleFiles}
              selectedIds={selectedFileIds}
              activePath={openFile?.filename || ''}
              searchQuery={searchQuery}
              searchMatches={searchMatches}
              busy={busy}
              onRefresh={async () => {
                await loadFiles();
                await refreshLocalTree();
              }}
              onToggleFile={(fileId) => setSelected((current) => ({ ...current, [fileId]: !current[fileId] }))}
              onOpenFile={(file) => {
                openWorkspaceFile(file);
                setEditorOpen(true);
              }}
              onSearchChange={setSearchQuery}
              onSearch={searchWorkspace}
              onUpload={uploadFiles}
              onCreateItem={trustedLocalPath ? createLocalWorkspaceItem : undefined}
              onCreateItemAtPath={trustedLocalPath ? createLocalWorkspaceItem : undefined}
              onRenameFile={trustedLocalPath ? renameLocalWorkspaceFile : undefined}
              onDeleteFile={trustedLocalPath ? deleteLocalWorkspaceFile : undefined}
              onRevealPath={trustedLocalPath ? revealLocalWorkspacePath : undefined}
              dirtyIds={openTabs.filter((tab) => tab.dirty).map((tab) => tab.id)}
              dirtyPaths={openTabs.filter((tab) => tab.dirty).map((tab) => tab.filename)}
              rootPath={trustedLocalPath}
              searchFocusKey={searchFocusKey}
            />
          </div>
        )}
        {rightPanelOpen && ['changes', 'jobs', 'preview', 'git'].includes(rightPanelView) && (
          <ActivityPanel
            events={events}
            jobs={jobs}
            workerStatus={workerStatus}
            patchPreview={patchPreview}
            commands={commands}
            runtimeStatus={runtimeStatus}
            githubStatus={githubStatus}
            githubRepositories={githubRepositories}
            githubBranches={githubBranches}
            selectedGithubRepo={selectedGithubRepo}
            deliveryPackage={engineeringDeliveryPackage}
            analysis={analysis}
            rollbackSnapshots={rollbackSnapshots}
            hasPatch={patchReady}
            canApply={patchReady && !!sessionId && !busy}
            canRunCommand={selectedFileIds.length > 0 && !busy}
            previewUrl={previewUrl}
            previewChecks={previewChecks}
            previewLogs={previewLogs}
            canCheckPreview={/^https?:\/\//.test(previewUrl.trim()) && !busy}
            canFixPreview={Boolean(sessionId) && !busy}
            canStartPreview={selectedFileIds.length > 0 && !busy}
            repoUrl={repoUrl}
            githubBaseBranch={githubBaseBranch}
            githubBranchName={githubBranchName}
            canUseGit={Boolean(sessionId) && !busy}
            onApply={applyChanges}
            onReject={rejectChanges}
            onApplySelection={applyPatchSelection}
            onRejectSelection={rejectPatchSelection}
            onApproveHunk={(hunkId) => updateHunkReview(hunkId, 'approve')}
            onRejectHunk={(hunkId) => updateHunkReview(hunkId, 'reject')}
            onResetPatchReview={resetPatchReview}
            onRollback={rollbackChanges}
            onRollbackSnapshot={rollbackSnapshot}
            onLoadRollbackSnapshots={() => loadRollbackSnapshots()}
            onRunCommand={runCommand}
            onRunChecks={runChecks}
            onInstallRuntime={installRuntime}
            onRefreshJobs={refreshCurrentJobs}
            onCancelJob={cancelJob}
            onPauseJob={pauseJob}
            onResumeJob={resumeJob}
            onRetryJob={retryJob}
            terminalSessions={Object.values(terminalSessions)}
            activeTerminalId={activeTerminalId}
            terminalCommand={terminalCommand}
            onCreateTerminal={createTerminal}
            onSelectTerminal={setActiveTerminalId}
            onTerminalCommandChange={setTerminalCommand}
            onSendTerminalInput={sendTerminalInput}
            onKillTerminal={killTerminal}
            canUseTerminal={canUseWorkspaceTerminal}
            terminalHelp={terminalHelp}
            onSyncRuntime={syncRuntime}
            onAnalyzeWorkspace={analyzeWorkspace}
            onPreviewUrlChange={setPreviewUrl}
            onCheckPreview={checkPreview}
            onFixPreview={fixPreviewIssue}
            onStartPreview={startLivePreview}
            onStopPreview={stopLivePreview}
            onLoadPreviewLogs={loadPreviewLogs}
            onRepoUrlChange={setRepoUrl}
            onGithubRepoChange={setSelectedGithubRepo}
            onGithubBaseBranchChange={setGithubBaseBranch}
            onGithubBranchNameChange={setGithubBranchName}
            onConnectGithubApp={connectGithubApp}
            onRefreshGithub={refreshGithubState}
            onCreateGithubBranch={createGithubBranch}
            onCommitGithubChanges={commitGithubChanges}
            onCheckGithubPrStatus={checkGithubPrStatus}
            onConnectRepo={connectRepo}
            onImportRepo={importRepo}
            onPreparePr={preparePr}
            onOpenPr={openGithubAppPr}
            onCommitAndOpenPr={commitAndOpenGithubPr}
            initialTab={rightDrawerInitialTab}
            onClose={() => setRightPanelOpen(false)}
            showTabs={false}
          />
        )}
        {rightPanelOpen && rightPanelView === 'apps' && (
          <WorkspaceAppsPanel
            githubStatus={githubStatus}
            runtimeStatus={runtimeStatus}
            busy={busy}
            onConnectGithub={connectGithubApp}
            onRefreshGithub={refreshGithubState}
            onSyncRuntime={syncRuntime}
            onRunChecks={runChecks}
          />
        )}
        {rightPanelOpen && rightPanelView === 'tasks' && (
          <ProjectNavigator
            task={navigatorTask}
            onAutomate={runWorkspace}
          />
        )}
        </div>
        {clientReady && (
        <WorkspaceTerminalPanel
          open={terminalPanelOpen}
          size={terminalPanelSize}
          sessions={Object.values(terminalSessions)}
          activeTerminalId={activeTerminalId}
          sessionId={sessionId}
          command={terminalCommand}
          canUseTerminal={canUseWorkspaceTerminal}
          helpText={terminalHelp}
          busy={busy}
          onClose={() => setTerminalPanelOpen(false)}
          onSizeChange={setTerminalPanelSize}
          onCreate={createTerminal}
          onSelect={setActiveTerminalId}
          onCommandChange={setTerminalCommand}
          onSend={sendTerminalInput}
          onRawInput={sendTerminalRawInput}
          onResize={resizeTerminal}
          onCloudFrame={handleCloudTerminalFrame}
          onKill={killTerminal}
          onRestart={restartTerminal}
          onClear={clearTerminal}
        />
        )}
        <WorkspaceRightRail
          rightPanelOpen={rightPanelOpen}
          rightPanelView={rightPanelView}
          terminalPanelOpen={terminalPanelOpen}
          visibleFileCount={visibleFiles.length}
          terminalSessions={terminalSessions}
          patchPreviewCount={patchPreview.length}
          jobs={jobs}
          previewChecks={previewChecks}
          workspaceTasks={workspaceTasks}
          onOpenRightTool={openRightTool}
          onToggleTerminal={() => setTerminalPanelOpen((current) => !current)}
          onToggleRightPanel={() => setRightPanelOpen((current) => !current)}
        />
      </div>
      {folderWatchError && (
        <div className={styles.watchErrorToast} role="status">
          <div>
            <strong>Folder watcher paused</strong>
            <span>{folderWatchError.message}</span>
          </div>
          <button type="button" onClick={retryFolderWatch}>Retry watching</button>
          <button type="button" aria-label="Dismiss folder watcher warning" onClick={() => setFolderWatchError(null)}>×</button>
        </div>
      )}
      {filesOpen && (
        <div className={styles.filesDrawerBackdrop} role="presentation" onMouseDown={() => setFilesOpen(false)}>
          <div className={styles.filesDrawer} role="dialog" aria-label="Project files" onMouseDown={(event) => event.stopPropagation()}>
            <div className={styles.drawerHeader}>
              <span>Project Files</span>
              <button type="button" onClick={() => setFilesOpen(false)}>Close</button>
            </div>
            <FileExplorer
              files={visibleFiles}
              selectedIds={selectedFileIds}
              activePath={openFile?.filename || ''}
              searchQuery={searchQuery}
              searchMatches={searchMatches}
              busy={busy}
              onRefresh={async () => {
                await loadFiles();
                await refreshLocalTree();
              }}
              onToggleFile={(fileId) => setSelected((current) => ({ ...current, [fileId]: !current[fileId] }))}
              onOpenFile={(file) => {
                openWorkspaceFile(file);
                setFilesOpen(false);
              }}
              onSearchChange={setSearchQuery}
              onSearch={searchWorkspace}
              onUpload={uploadFiles}
              onCreateItem={trustedLocalPath ? createLocalWorkspaceItem : undefined}
              onCreateItemAtPath={trustedLocalPath ? createLocalWorkspaceItem : undefined}
              onRenameFile={trustedLocalPath ? renameLocalWorkspaceFile : undefined}
              onDeleteFile={trustedLocalPath ? deleteLocalWorkspaceFile : undefined}
              onRevealPath={trustedLocalPath ? revealLocalWorkspacePath : undefined}
              dirtyIds={openTabs.filter((tab) => tab.dirty).map((tab) => tab.id)}
              dirtyPaths={openTabs.filter((tab) => tab.dirty).map((tab) => tab.filename)}
              rootPath={trustedLocalPath}
              searchFocusKey={searchFocusKey}
            />
          </div>
        </div>
      )}
      {pendingProjectOpen && (
        <div className={styles.replaceDialogBackdrop} role="presentation" onMouseDown={() => setPendingProjectOpen(null)}>
          <div className={styles.replaceDialog} role="dialog" aria-label="Replace open project" onMouseDown={(event) => event.stopPropagation()}>
            <strong>Three projects are already open</strong>
            <p>Close one open project tab to open the next workspace. This will not delete any files or archive the project.</p>
            <div className={styles.replaceProjectList}>
              {openProjects.map((project) => (
                <button key={project.id} type="button" onClick={() => void replaceOpenProject(project.id)}>
                  <span>{project.name}</span>
                  <em>{project.local_workspace_path || `${project.file_count ?? project.file_ids?.length ?? 0} files`}</em>
                </button>
              ))}
            </div>
            <button type="button" className={styles.replaceCancel} onClick={() => setPendingProjectOpen(null)}>Cancel</button>
          </div>
        </div>
      )}
      <WorkspaceUpgradeDialog upgradePrompt={upgradePrompt} onClose={() => setUpgradePrompt(null)} />
      {onboardingOpen && (
        <OnboardingWizard
          onComplete={handleOnboardingComplete}
          onSelectDirectory={() => void importLocalDirectory('')}
        />
      )}
      <input
        ref={fileInputRef}
        hidden
        multiple
        type="file"
        accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css,.pdf,.docx,.xlsx,.zip"
        onChange={(event) => uploadFiles(event.target.files)}
      />
      </main>
    </DesktopOnlyGuard>
  );
}
