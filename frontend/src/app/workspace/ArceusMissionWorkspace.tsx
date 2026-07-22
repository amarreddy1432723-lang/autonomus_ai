'use client';

import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronDown,
  Circle,
  ClipboardCheck,
  Code2,
  FileCode2,
  FileText,
  Folder,
  GitBranch,
  Loader2,
  Play,
  Plus,
  Save,
  Search,
  Terminal,
  Undo2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityBar,
  AppShell,
  BottomPanel,
  EditorWorkspace,
  WorkspaceSidebar,
  WorkspaceStatusBar,
  WorkspaceTopBar,
} from '../../components/workspace';
import { useWorkspaceLayoutStore } from '../../stores/workspace-layout-store';
import { useRepositoryStore, type RepositoryState } from '../../stores/repository-store';
import { useMissionStore, type PersistedMission } from '../../stores/mission-store';
import { probeServiceHealth, type ServiceHealthSnapshot } from '../../utils/serviceHealth';
import styles from './ArceusMissionWorkspace.module.css';

type FileNode = {
  name: string;
  path: string;
  kind: 'folder' | 'file';
  level: number;
  active?: boolean;
  dirty?: boolean;
  sizeBytes?: number;
};

type OpenFile = {
  path: string;
  content: string;
  savedContent: string;
  sizeBytes?: number;
};

type MissionEvent = {
  id: string;
  title: string;
  detail: string;
  state: 'done' | 'running' | 'waiting' | 'blocked';
};

const bottomTabs = ['Terminal', 'Problems', 'Output', 'Tests', 'Logs'];
const terminalHistoryKey = 'arceus.workspace.localTerminalOutput.v1';

function filenameFromPath(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

function projectNameFromPath(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() || 'Workspace';
}

function normalizeTree(items: Array<Record<string, unknown>>, activePath?: string, dirtyPath?: string): FileNode[] {
  return items
    .map((item) => {
      const path = String(item.path || '');
      const normalized = path.replace(/\\/g, '/');
      const parts = normalized.split('/').filter(Boolean);
      const kind: FileNode['kind'] = item.type === 'folder' || item.kind === 'folder' ? 'folder' : 'file';
      return {
        name: parts.at(-1) || normalized,
        path: normalized,
        kind,
        level: Math.max(0, parts.length - 1),
        active: normalized === activePath,
        dirty: normalized === dirtyPath,
        sizeBytes: Number(item.size_bytes || 0),
      };
    })
    .filter((item) => item.path)
    .sort((a, b) => {
      const aFolder = a.kind === 'folder' ? 0 : 1;
      const bFolder = b.kind === 'folder' ? 0 : 1;
      if (a.level !== b.level) return a.path.localeCompare(b.path);
      if (aFolder !== bFolder) return aFolder - bFolder;
      return a.name.localeCompare(b.name);
    });
}

function ipcResult<T>(result: DesktopIpcResponse<T> | T): T {
  if (result && typeof result === 'object' && 'ok' in result) {
    const wrapped = result as DesktopIpcResponse<T>;
    if (!wrapped.ok) throw new Error(wrapped.error?.message || 'Desktop action failed.');
    return wrapped.result as T;
  }
  return result as T;
}

function stateIcon(state: MissionEvent['state']) {
  if (state === 'done') return <CheckCircle2 size={14} />;
  if (state === 'running') return <Loader2 size={14} className={styles.spin} />;
  if (state === 'blocked') return <AlertCircle size={14} />;
  return <Circle size={14} />;
}

function ExplorerPanel({
  rootPath,
  files,
  busy,
  error,
  onOpenFolder,
  onRefresh,
  onOpenFile,
}: {
  rootPath: string;
  files: FileNode[];
  busy: boolean;
  error: string;
  onOpenFolder: () => void;
  onRefresh: () => void;
  onOpenFile: (file: FileNode) => void;
}) {
  const [filter, setFilter] = useState('');
  const visibleFiles = useMemo(() => {
    const value = filter.trim().toLowerCase();
    if (!value) return files;
    return files.filter((file) => file.path.toLowerCase().includes(value));
  }, [files, filter]);

  return (
    <WorkspaceSidebar
      title="Explorer"
      action={
        <button type="button" className={styles.iconButton} aria-label="New file" disabled={!rootPath}>
          <Plus size={14} />
        </button>
      }
    >
      <div className={styles.explorerHeader}>
        <button type="button" className={styles.openFolderButton} onClick={onOpenFolder} disabled={busy}>
          <Folder size={14} />
          Open Folder
        </button>
        <label className={styles.sidebarSearch}>
          <Search size={13} />
          <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search files" />
        </label>
        <div className={styles.pathLine} title={rootPath || 'No folder opened'}>
          {rootPath || 'No folder opened'}
        </div>
        {error && <div className={styles.inlineError}>{error}</div>}
      </div>
      <div className={styles.fileTree}>
        {visibleFiles.map((file) => (
          <button
            key={file.path}
            type="button"
            className={styles.fileRow}
            data-active={file.active || undefined}
            data-dirty={file.dirty || undefined}
            disabled={file.kind === 'folder'}
            onClick={() => onOpenFile(file)}
            style={{ paddingLeft: 10 + file.level * 12 }}
          >
            {file.kind === 'folder' ? <Folder size={13} /> : <FileText size={13} />}
            <span>{file.name}</span>
          </button>
        ))}
        {!rootPath && <div className={styles.emptyMini}>Open a trusted folder to start editing.</div>}
        {rootPath && visibleFiles.length === 0 && <div className={styles.emptyMini}>No matching files.</div>}
      </div>
      <div className={styles.sidebarFooter}>
        <button type="button" onClick={onRefresh} disabled={!rootPath || busy}>Refresh tree</button>
      </div>
    </WorkspaceSidebar>
  );
}

function EditorPane({
  openFile,
  rootPath,
  saving,
  onChange,
  onSave,
}: {
  openFile: OpenFile | null;
  rootPath: string;
  saving: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
}) {
  const dirty = Boolean(openFile && openFile.content !== openFile.savedContent);

  if (!openFile) {
    return (
      <EditorWorkspace>
        <div className={styles.emptyEditor}>
          <Code2 size={28} />
          <strong>{rootPath ? 'Select a file to inspect' : 'Open a folder to begin'}</strong>
          <p>Arceus Code keeps local file editing and terminal execution available even when cloud services are offline.</p>
        </div>
      </EditorWorkspace>
    );
  }

  return (
    <EditorWorkspace>
      <section className={styles.editor}>
        <div className={styles.editorTabs}>
          <button type="button" data-active="true">
            <FileCode2 size={13} />
            <span>{dirty ? '* ' : ''}{filenameFromPath(openFile.path)}</span>
          </button>
        </div>
        <div className={styles.editorToolbar}>
          <span title={openFile.path}>{openFile.path}</span>
          <div>
            <button type="button" disabled>
              <Play size={13} />
              Run checks
            </button>
            <button type="button" onClick={onSave} disabled={!dirty || saving}>
              <Save size={13} />
              {saving ? 'Saving' : 'Save'}
            </button>
            <button type="button">
              <GitBranch size={13} />
              main
            </button>
          </div>
        </div>
        <textarea
          className={styles.editorTextarea}
          value={openFile.content}
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
        />
      </section>
    </EditorWorkspace>
  );
}

function MissionPanel({
  health,
  repository,
  mission,
  missionStatus,
  missionError,
  events,
  onRetry,
  onOpenDiagnostics,
  onCreateMission,
  onApproveMission,
  onRejectMission,
  onClearMission,
}: {
  health: ServiceHealthSnapshot | null;
  repository: RepositoryState;
  mission: PersistedMission | null;
  missionStatus: 'idle' | 'creating' | 'awaiting_approval' | 'queuing' | 'queued' | 'rejected' | 'failed';
  missionError: string;
  events: MissionEvent[];
  onRetry: () => void;
  onOpenDiagnostics: () => void;
  onCreateMission: (goal: string) => void;
  onApproveMission: () => void;
  onRejectMission: () => void;
  onClearMission: () => void;
}) {
  const toggleAIPanel = useWorkspaceLayoutStore((state) => state.toggleAIPanel);
  const online = health?.state === 'online';
  const [goal, setGoal] = useState('');
  const isMissionBusy = missionStatus === 'creating' || missionStatus === 'queuing';
  const canSubmit = online && repository.status === 'ready' && goal.trim().length > 2 && !isMissionBusy;
  const understanding = mission?.compiled_plan?.understanding || {};
  const plannedTasks = mission?.compiled_plan?.tasks || [];

  return (
    <aside className={styles.aiPanel}>
      <header className={styles.aiHeader}>
        <div>
          <strong>Arceus Agent</strong>
          <span>{health?.label || 'Checking services'}</span>
        </div>
        <button type="button" className={styles.iconButton} aria-label="Hide agent panel" onClick={toggleAIPanel}>
          <ChevronDown size={15} />
        </button>
      </header>

      <section className={styles.receipt} data-offline={!online || undefined}>
        <div className={styles.receiptTop}>
          <span className={online ? styles.successBadge : styles.warningBadge}>{health?.label || 'Checking'}</span>
          <strong>{online ? 'Agent ready' : 'Local mode active'}</strong>
        </div>
        <p>{health?.detail || 'Checking the agent API and account connection.'}</p>
        <div className={styles.receiptGrid}>
          <span><b>Files</b> Local</span>
          <span><b>Editor</b> Writable</span>
          <span><b>Agent</b> {online ? 'Ready' : 'Paused'}</span>
        </div>
        <div className={styles.receiptActions}>
          <button type="button" onClick={onRetry}><Undo2 size={14} /> Retry services</button>
          <button type="button" onClick={onOpenDiagnostics}><ClipboardCheck size={14} /> Diagnostics</button>
        </div>
      </section>

      <section className={styles.repositoryCard} data-status={repository.status}>
        <div className={styles.repositoryCardTop}>
          <strong>Repository</strong>
          <span>{repository.status === 'analyzing' ? 'Analyzing...' : repository.status === 'ready' ? 'Ready' : repository.status === 'failed' ? 'Failed' : 'Idle'}</span>
        </div>
        {repository.status === 'ready' ? (
          <>
            <p>{repository.summary}</p>
            <div className={styles.repoFacts}>
              <span><b>{repository.scannedFiles}</b> files scanned</span>
              <span><b>{repository.frameworks.slice(0, 2).join(', ') || 'Unknown'}</b> frameworks</span>
              <span><b>{repository.architectureStyle || 'Unknown'}</b> architecture</span>
            </div>
            <div className={styles.repoSignals}>
              {[...repository.languages.slice(0, 4), ...repository.databaseUsage, ...repository.authentication].slice(0, 8).map((signal) => (
                <span key={signal}>{signal}</span>
              ))}
            </div>
          </>
        ) : repository.status === 'failed' ? (
          <p>{repository.error || 'Repository analysis failed.'}</p>
        ) : repository.status === 'analyzing' ? (
          <div className={styles.analysisSteps}>
            <span><Loader2 size={13} className={styles.spin} /> Scanning files</span>
            <span>Detecting frameworks</span>
            <span>Finding entry points and tests</span>
          </div>
        ) : (
          <p>Open a folder to trigger repository intelligence.</p>
        )}
      </section>

      <section className={styles.timeline}>
        {events.map((event) => (
          <article key={event.id} data-state={event.state}>
            {stateIcon(event.state)}
            <div>
              <strong>{event.title}</strong>
              <p>{event.detail}</p>
            </div>
          </article>
        ))}
      </section>

      {mission && (
        <section className={styles.missionPlanCard} data-state={mission.display_status === 'awaiting_approval' ? 'AWAITING_APPROVAL' : mission.status.toUpperCase()}>
          <div className={styles.missionPlanTop}>
            <span>{mission.display_status === 'queued' ? 'Mission queued' : mission.display_status === 'awaiting_approval' ? 'Plan needs approval' : mission.display_status}</span>
            <button type="button" onClick={onClearMission}>Clear</button>
          </div>
          <strong>{mission.goal}</strong>
          <p>{understanding.intent || 'mission'} / {understanding.domain || 'software'} / {understanding.risk_level || 'medium'} risk</p>
          <div className={styles.missionPlanStats}>
            <span><b>{mission.task_count}</b> tasks</span>
            <span><b>{mission.dependency_count}</b> dependencies</span>
            <span><b>{Math.round(mission.confidence * 100)}%</b> confidence</span>
          </div>
          <div className={styles.taskChips}>
            {(mission.tasks.length ? mission.tasks : plannedTasks).slice(0, 6).map((task) => (
              <span key={task.task_key}>{task.title}</span>
            ))}
          </div>
          <div className={styles.agentRows}>
            {mission.agents.slice(0, 4).map((agent) => (
              <span key={agent}><b>{agent}</b>{mission.display_status}</span>
            ))}
          </div>
          {mission.warnings.length > 0 && <p className={styles.planWarning}>{mission.warnings[0]}</p>}
          <div className={styles.receiptActions}>
            <button type="button" onClick={onApproveMission} disabled={!mission.approval_required || isMissionBusy}>
              <CheckCircle2 size={14} />
              {missionStatus === 'queuing' ? 'Queuing' : 'Approve and queue'}
            </button>
            <button type="button" onClick={onRejectMission} disabled={!mission.approval_required || isMissionBusy}>
              <AlertCircle size={14} />
              Reject
            </button>
          </div>
        </section>
      )}

      <form
        className={styles.composer}
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSubmit) return;
          onCreateMission(goal);
        }}
      >
        <textarea
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          disabled={!online}
          placeholder={online ? 'Describe the mission. Example: Implement Google OAuth and verify it with tests.' : 'Connect services to use the cloud agent. Local files and terminal still work.'}
        />
        {missionError && <span className={styles.inlineError}>{missionError}</span>}
        <div>
          <button type="button" className={styles.modeButton} disabled={!online}>
            <Code2 size={14} />
            Auto
          </button>
          <button type="submit" className={styles.sendButton} disabled={!canSubmit}>
            {missionStatus === 'creating' ? <Loader2 size={15} className={styles.spin} /> : <Bot size={15} />}
          </button>
        </div>
      </form>
    </aside>
  );
}

function WorkspaceBottomPanel({
  rootPath,
  terminalId,
  terminalOutput,
  terminalCommand,
  terminalStatus,
  onCommandChange,
  onCreateTerminal,
  onSendCommand,
  onKillTerminal,
}: {
  rootPath: string;
  terminalId: string;
  terminalOutput: string[];
  terminalCommand: string;
  terminalStatus: string;
  onCommandChange: (value: string) => void;
  onCreateTerminal: () => void;
  onSendCommand: () => void;
  onKillTerminal: () => void;
}) {
  const [activeTab, setActiveTab] = useState('Terminal');

  return (
    <BottomPanel title="Execution">
      <section className={styles.bottomPanel}>
        <div className={styles.bottomTabs}>
          {bottomTabs.map((tab) => (
            <button key={tab} type="button" data-active={tab === activeTab || undefined} onClick={() => setActiveTab(tab)}>
              {tab === 'Terminal' ? <Terminal size={14} /> : <ClipboardCheck size={14} />}
              {tab}
            </button>
          ))}
        </div>
        {activeTab === 'Terminal' ? (
          <div className={styles.terminalPane}>
            <div className={styles.terminalMeta}>
              <span title={rootPath}>{rootPath || 'Open a folder to bind terminal cwd'}</span>
              <strong>{terminalStatus}</strong>
              <button type="button" onClick={onCreateTerminal} disabled={!rootPath}>New terminal</button>
              <button type="button" onClick={onKillTerminal} disabled={!terminalId}>Kill</button>
            </div>
            <pre className={styles.terminalSurface}>
              {terminalOutput.length ? terminalOutput.join('') : 'No terminal output yet.'}
            </pre>
            <form
              className={styles.terminalCommand}
              onSubmit={(event) => {
                event.preventDefault();
                onSendCommand();
              }}
            >
              <span>PS</span>
              <input
                value={terminalCommand}
                onChange={(event) => onCommandChange(event.target.value)}
                disabled={!terminalId}
                placeholder={terminalId ? 'Run a command in this workspace' : 'Create a terminal first'}
              />
              <button type="submit" disabled={!terminalId || !terminalCommand.trim()}>Run</button>
            </form>
          </div>
        ) : (
          <div className={styles.placeholderPanel}>
            <strong>{activeTab}</strong>
            <p>This panel is ready for the legacy {activeTab.toLowerCase()} data extraction.</p>
          </div>
        )}
      </section>
    </BottomPanel>
  );
}

export default function ArceusMissionWorkspace() {
  const [rootPath, setRootPath] = useState('');
  const [projectName, setProjectName] = useState('Workspace');
  const [files, setFiles] = useState<FileNode[]>([]);
  const [openFile, setOpenFile] = useState<OpenFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState<ServiceHealthSnapshot | null>(null);
  const [terminalId, setTerminalId] = useState('');
  const [terminalStatus, setTerminalStatus] = useState('idle');
  const [terminalOutput, setTerminalOutput] = useState<string[]>([]);
  const [terminalCommand, setTerminalCommand] = useState('');
  const terminalIdRef = useRef('');
  const repository = useRepositoryStore();
  const missionRuntime = useMissionStore();

  useEffect(() => {
    terminalIdRef.current = terminalId;
  }, [terminalId]);

  const dirtyPath = openFile && openFile.content !== openFile.savedContent ? openFile.path : '';

  const refreshHealth = useCallback(async () => {
    const snapshot = await probeServiceHealth({ timeoutMs: 2500 });
    setHealth(snapshot);
  }, []);

  useEffect(() => {
    void refreshHealth();
    const timer = window.setInterval(() => void refreshHealth(), 30000);
    return () => window.clearInterval(timer);
  }, [refreshHealth]);

  const refreshTree = useCallback(async (pathValue = rootPath, activePath = openFile?.path) => {
    if (!pathValue) return;
    setBusy(true);
    setError('');
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      const tree = desktop?.workspace?.readDirectoryTree
        ? await desktop.workspace.readDirectoryTree(pathValue)
        : await legacy?.readDirectoryTree?.(pathValue);
      setFiles(normalizeTree(tree?.items || [], activePath, dirtyPath || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not refresh local folder.');
    } finally {
      setBusy(false);
    }
  }, [dirtyPath, openFile?.path, rootPath]);

  const openFolder = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      let selectedPath = '';
      if (desktop?.workspace?.openDirectory) {
        const workspace = ipcResult(await desktop.workspace.openDirectory({ trusted: true }));
        selectedPath = workspace?.rootPath || '';
      } else if (legacy?.selectDirectory) {
        selectedPath = await legacy.selectDirectory();
      }
      if (!selectedPath) return;
      setRootPath(selectedPath);
      setProjectName(projectNameFromPath(selectedPath));
      setOpenFile(null);
      legacy?.watchDirectory?.(selectedPath);
      await refreshTree(selectedPath, '');
      void repository.analyzeRepository(selectedPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open folder.');
    } finally {
      setBusy(false);
    }
  }, [refreshTree]);

  const openLocalFile = useCallback(async (file: FileNode) => {
    if (!rootPath || file.kind !== 'file') return;
    setBusy(true);
    setError('');
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      const data = desktop?.filesystem?.readFile
        ? ipcResult(await desktop.filesystem.readFile(rootPath, file.path))
        : await legacy?.readFile?.(rootPath, file.path);
      const nextFile = {
        path: data.path || file.path,
        content: data.content || '',
        savedContent: data.content || '',
        sizeBytes: data.size_bytes,
      };
      setOpenFile(nextFile);
      setFiles((current) => current.map((item) => ({ ...item, active: item.path === nextFile.path, dirty: false })));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open file.');
    } finally {
      setBusy(false);
    }
  }, [rootPath]);

  const saveLocalFile = useCallback(async () => {
    if (!rootPath || !openFile) return;
    setSaving(true);
    setError('');
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      if (desktop?.filesystem?.writeFile) {
        ipcResult(await desktop.filesystem.writeFile(rootPath, openFile.path, openFile.content));
      } else {
        await legacy?.writeFile?.(rootPath, openFile.path, openFile.content);
      }
      setOpenFile((current) => current ? { ...current, savedContent: current.content } : current);
      setFiles((current) => current.map((item) => item.path === openFile.path ? { ...item, dirty: false } : item));
      await refreshTree(rootPath, openFile.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save file.');
    } finally {
      setSaving(false);
    }
  }, [openFile, refreshTree, rootPath]);

  const createTerminal = useCallback(async () => {
    if (!rootPath) return;
    setError('');
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      const session = desktop?.terminal?.create
        ? ipcResult(await desktop.terminal.create(rootPath, { cols: 100, rows: 28, shell: 'powershell' }))
        : await legacy?.terminalCreate?.(rootPath, { cols: 100, rows: 28, shell: 'powershell' });
      setTerminalId(session.id);
      setTerminalStatus(session.status || 'running');
      const intro = `\r\nArceus local terminal ready: ${session.cwd || rootPath}\r\n`;
      setTerminalOutput((current) => [...current, intro]);
      window.localStorage.setItem(terminalHistoryKey, JSON.stringify([...terminalOutput, intro].slice(-200)));
    } catch (err) {
      setTerminalStatus('failed');
      setError(err instanceof Error ? err.message : 'Could not create terminal.');
    }
  }, [rootPath, terminalOutput]);

  const sendTerminalCommand = useCallback(async () => {
    const command = terminalCommand.trim();
    if (!terminalId || !command) return;
    setTerminalCommand('');
    setTerminalOutput((current) => [...current, `\r\n> ${command}\r\n`]);
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      if (desktop?.terminal?.sendInput) {
        ipcResult(await desktop.terminal.sendInput(terminalId, command));
      } else {
        await legacy?.terminalInput?.(terminalId, command);
      }
    } catch (err) {
      setTerminalStatus('failed');
      setTerminalOutput((current) => [...current, `\r\nError: ${err instanceof Error ? err.message : 'command failed'}\r\n`]);
    }
  }, [terminalCommand, terminalId]);

  const killTerminal = useCallback(async () => {
    if (!terminalId) return;
    try {
      const desktop = window.arceusDesktop;
      const legacy = (window as any).electron;
      if (desktop?.terminal?.kill) {
        ipcResult(await desktop.terminal.kill(terminalId));
      } else {
        await legacy?.terminalKill?.(terminalId);
      }
    } finally {
      setTerminalStatus('killed');
      setTerminalId('');
    }
  }, [terminalId]);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(terminalHistoryKey) || '[]');
      if (Array.isArray(stored)) setTerminalOutput(stored.slice(-120).map(String));
    } catch {
      setTerminalOutput([]);
    }
  }, []);

  useEffect(() => {
    const desktop = window.arceusDesktop;
    const legacy = (window as any).electron;
    const onData = (payload: { id: string; data: string }) => {
      if (payload.id !== terminalIdRef.current) return;
      setTerminalOutput((current) => {
        const next = [...current, payload.data].slice(-260);
        window.localStorage.setItem(terminalHistoryKey, JSON.stringify(next));
        return next;
      });
    };
    const onExit = (payload: { id: string; code: number | null; signal?: string | null }) => {
      if (payload.id !== terminalIdRef.current) return;
      setTerminalStatus(payload.signal ? 'killed' : `exited ${payload.code ?? ''}`.trim());
      setTerminalId('');
    };
    const offData = desktop?.terminal?.onData ? desktop.terminal.onData(onData) : legacy?.onTerminalData?.(onData);
    const offExit = desktop?.terminal?.onExit ? desktop.terminal.onExit(onExit) : legacy?.onTerminalExit?.(onExit);
    return () => {
      offData?.();
      offExit?.();
    };
  }, []);

  useEffect(() => {
    const legacy = (window as any).electron;
    if (!legacy?.onDirectoryChanged) return undefined;
    const unsubscribe = legacy.onDirectoryChanged(() => {
      void refreshTree(rootPath, openFile?.path);
    });
    return () => unsubscribe?.();
  }, [openFile?.path, refreshTree, rootPath]);

  const events: MissionEvent[] = useMemo(() => [
    {
      id: 'folder',
      title: rootPath ? 'Folder connected' : 'Waiting for folder',
      detail: rootPath || 'Open a trusted local folder to enable explorer, editor and terminal.',
      state: rootPath ? 'done' : 'waiting',
    },
    {
      id: 'file',
      title: openFile ? 'File loaded' : 'Editor ready',
      detail: openFile ? openFile.path : 'Select a file from Explorer to inspect and edit.',
      state: openFile ? 'done' : 'waiting',
    },
    {
      id: 'terminal',
      title: terminalId ? 'Terminal running' : 'Terminal idle',
      detail: terminalId ? 'Local terminal is bound to the trusted workspace folder.' : 'Create a terminal from the bottom panel.',
      state: terminalId ? 'running' : 'waiting',
    },
    {
      id: 'agent',
      title: health?.label || 'Checking agent',
      detail: health?.detail || 'Service health check is running.',
      state: health?.state === 'online' ? 'done' : health?.state === 'offline_local_only' ? 'blocked' : 'waiting',
    },
    {
      id: 'repository',
      title: repository.status === 'ready' ? 'Repository analyzed' : repository.status === 'analyzing' ? 'Repository analyzing' : 'Repository intelligence',
      detail: repository.summary || repository.error || 'Analysis starts automatically after a folder opens.',
      state: repository.status === 'ready' ? 'done' : repository.status === 'failed' ? 'blocked' : 'waiting',
    },
    {
      id: 'mission',
      title: missionRuntime.mission
        ? missionRuntime.mission.display_status === 'queued'
          ? 'Mission queued'
          : 'Mission awaiting approval'
        : 'Mission runtime',
      detail: missionRuntime.mission
        ? `${missionRuntime.mission.task_count} tasks, ${missionRuntime.mission.dependency_count} dependencies`
        : 'Describe a goal to create a durable engineering mission.',
      state: missionRuntime.mission?.display_status === 'queued' ? 'running' : missionRuntime.mission ? 'waiting' : 'waiting',
    },
  ], [health, missionRuntime.mission, openFile, repository.error, repository.status, repository.summary, rootPath, terminalId]);

  return (
    <AppShell
      topBar={
        <WorkspaceTopBar
          projectName="Arceus Code"
          repositoryName={projectName}
          missionStatus={health?.state === 'online' ? 'idle' : health?.state === 'offline_local_only' ? 'waiting' : 'running'}
          selectedModel={health?.label || 'Checking'}
          userName={health?.authReady ? 'VK' : 'Connect'}
        />
      }
      activityBar={<ActivityBar />}
      sidebar={
        <ExplorerPanel
          rootPath={rootPath}
          files={files.map((file) => ({
            ...file,
            active: file.path === openFile?.path,
            dirty: file.path === dirtyPath,
          }))}
          busy={busy}
          error={error}
          onOpenFolder={openFolder}
          onRefresh={() => void refreshTree()}
          onOpenFile={openLocalFile}
        />
      }
      editor={
        <EditorPane
          rootPath={rootPath}
          openFile={openFile}
          saving={saving}
          onChange={(content) => {
            setOpenFile((current) => current ? { ...current, content } : current);
            setFiles((current) => current.map((item) => item.path === openFile?.path ? { ...item, dirty: true } : item));
          }}
          onSave={saveLocalFile}
        />
      }
      assistant={
        <MissionPanel
          health={health}
          repository={repository}
          mission={missionRuntime.mission}
          missionStatus={missionRuntime.status}
          missionError={missionRuntime.error}
          events={events}
          onRetry={refreshHealth}
          onOpenDiagnostics={() => void window.arceusDesktop?.diagnostics?.()}
          onCreateMission={(goal) => void missionRuntime.createMission(goal, repository)}
          onApproveMission={() => void missionRuntime.approveMission()}
          onRejectMission={() => void missionRuntime.rejectMission()}
          onClearMission={missionRuntime.clearMission}
        />
      }
      bottomPanel={
        <WorkspaceBottomPanel
          rootPath={rootPath}
          terminalId={terminalId}
          terminalOutput={terminalOutput}
          terminalCommand={terminalCommand}
          terminalStatus={terminalStatus}
          onCommandChange={setTerminalCommand}
          onCreateTerminal={createTerminal}
          onSendCommand={sendTerminalCommand}
          onKillTerminal={killTerminal}
        />
      }
      statusBar={
        <WorkspaceStatusBar
          branch="main"
          diagnostics={error ? 1 : 0}
          serviceState={health?.label || 'Checking'}
          modelState={repository.status === 'ready' ? `${repository.scannedFiles} files indexed` : rootPath ? 'Analyzing repository' : 'No folder'}
        />
      }
    />
  );
}
