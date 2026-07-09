'use client';

import { MoreHorizontal, UserCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import DesktopOnlyGuard from '../../components/DesktopOnlyGuard';
import { apiRequest, createApiHeadersAsync } from '../../utils/api';
import ActivityPanel, { ActivityEvent, AgentJob, PatchPreviewItem, PreviewCheck, PreviewLogs, RollbackSnapshot, WorkspaceAnalysis, WorkspaceCommand } from './ActivityPanel';
import ConversationPanel, { WorkspaceMessage, WorkspaceMode } from './ConversationPanel';
import EditorPanel, { OpenWorkspaceFile } from './EditorPanel';
import FileExplorer, { WorkspaceFile, WorkspaceSearchMatch } from './FileExplorer';
import WorkspaceSidebar, { WorkspaceRecentItem } from './WorkspaceSidebar';
import styles from './Workspace.module.css';

const model = { llm_provider: 'nexus', llm_model: 'nexus-code' };

type CodeProject = {
  id: string;
  name: string;
  description?: string;
  repo_url?: string;
  status?: string;
  file_ids?: string[];
  active_session_id?: string | null;
  last_opened_at?: string | null;
};

function id(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function inferModes(prompt: string, selected: WorkspaceMode): WorkspaceMode[] {
  if (selected !== 'auto') return [selected];
  const text = prompt.toLowerCase();
  const modes: WorkspaceMode[] = [];
  if (/(research|latest|best practice|compare|search|find)/.test(text)) modes.push('research');
  if (/(design|ui|ux|screen|layout|component|page)/.test(text)) modes.push('design');
  if (/(deploy|railway|vercel|render|production|release)/.test(text)) modes.push('deploy');
  if (/(code|build|fix|bug|api|endpoint|implement|refactor|test)/.test(text)) modes.push('code');
  return modes.length ? modes : ['code'];
}

function summarizePatch(raw: string) {
  try {
    const payload = JSON.parse(raw);
    const files = Array.isArray(payload.files) ? payload.files : [];
    return files.map((file: any) => `✏️ ${file.filename || file.file_id || 'file'}\nFull replacement prepared.`).join('\n\n') || raw;
  } catch {
    return raw;
  }
}

function summarizePreview(preview: Array<{ filename: string; additions?: number; deletions?: number }>) {
  if (!preview.length) return 'Patch prepared for review.';
  return preview
    .map((file) => `Edited ${file.filename}: +${file.additions || 0} / -${file.deletions || 0}`)
    .join('\n');
}

function normalizeEvents(events: any[]): ActivityEvent[] {
  return [...(events || [])].reverse().map((event, index) => ({
    id: event.id || `stored-${index}`,
    kind: event.kind || 'start',
    message: event.message || 'Workspace activity',
    detail: event.detail,
    diff: event.diff,
  }));
}

export default function WorkspacePage() {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [jobs, setJobs] = useState<AgentJob[]>([]);
  const [commands, setCommands] = useState<WorkspaceCommand[]>([]);
  const [analysis, setAnalysis] = useState<WorkspaceAnalysis | null>(null);
  const [rollbackSnapshots, setRollbackSnapshots] = useState<RollbackSnapshot[]>([]);
  const [mode, setMode] = useState<WorkspaceMode>('auto');
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [patchReady, setPatchReady] = useState(false);
  const [patchPreview, setPatchPreview] = useState<PatchPreviewItem[]>([]);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewLogs, setPreviewLogs] = useState<PreviewLogs | null>(null);
  const [previewChecks, setPreviewChecks] = useState<PreviewCheck[]>([]);
  const [repoUrl, setRepoUrl] = useState('');
  const [openTabs, setOpenTabs] = useState<OpenWorkspaceFile[]>([]);
  const [activeFileId, setActiveFileId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMatches, setSearchMatches] = useState<WorkspaceSearchMatch[]>([]);
  const [searchFocusKey, setSearchFocusKey] = useState(0);
  const [filesOpen, setFilesOpen] = useState(false);
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [projectId, setProjectId] = useState('');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedFileIds = useMemo(
    () => Object.entries(selected).filter(([, value]) => value).map(([fileId]) => fileId),
    [selected]
  );

  const activeProject = useMemo(
    () => projects.find((project) => project.id === projectId) || null,
    [projectId, projects]
  );

  const openFile = useMemo(
    () => openTabs.find((file) => file.id === activeFileId) || openTabs[0] || null,
    [activeFileId, openTabs]
  );

  const recentItems = useMemo<WorkspaceRecentItem[]>(() => {
    const projectItems = projects.slice(0, 5).map((project) => ({
      id: `project-${project.id}`,
      label: project.name,
      detail: project.repo_url || `${project.file_ids?.length || 0} file${project.file_ids?.length === 1 ? '' : 's'}`,
      kind: 'project' as const,
    }));
    const jobItems = jobs.slice(0, 4).map((job) => ({
      id: `job-${job.id}`,
      label: job.prompt || `${job.mode || 'Agent'} job`,
      detail: job.status || 'job',
      kind: 'job' as const,
    }));
    const fileItems = files.slice(0, 4).map((file) => ({
      id: `file-${file.id}`,
      label: file.filename,
      detail: file.content_type || 'workspace file',
      kind: 'file' as const,
    }));
    return [...projectItems, ...jobItems, ...fileItems].slice(0, 8);
  }, [files, jobs, projects]);

  const addEvent = (event: Omit<ActivityEvent, 'id'>) => {
    setEvents((current) => [{ ...event, id: id('evt') }, ...current].slice(0, 80));
  };

  const addMessage = (role: WorkspaceMessage['role'], content: string) => {
    setMessages((current) => [...current, { id: id(role), role, content }]);
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
    setAnalysis(null);
    setRollbackSnapshots([]);
    setPatchPreview([]);
    setPatchReady(false);
    setPreviewChecks([]);
    setPreviewLogs(null);
    setOpenTabs([]);
    setActiveFileId('');
    setSearchMatches([]);
  };

  const createProject = async () => {
    if (busy) return;
    const fallbackName = `NEXUS Code Project ${new Date().toLocaleDateString()}`;
    const name = window.prompt('Project name', fallbackName)?.trim() || fallbackName;
    setBusy(true);
    try {
      resetWorkspaceForProject();
      const project = await apiRequest('/api/v1/code/projects', {
        method: 'POST',
        body: JSON.stringify({ name, file_ids: [] }),
      });
      setProjectId(project.id);
      if (project.session?.id) {
        setSessionId(project.session.id);
        localStorage.setItem('nexus.code.session_id', project.session.id);
      }
      await loadProjects();
      addEvent({ kind: 'start', message: 'Code project created', detail: name });
      setFilesOpen(true);
      setTimeout(() => fileInputRef.current?.click(), 0);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Create project failed', detail: error instanceof Error ? error.message : 'Could not create project.' });
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

  const openCodeProject = async (idValue: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const project = await apiRequest(`/api/v1/code/projects/${idValue}`);
      setProjectId(project.id);
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
      addEvent({ kind: 'error', message: 'Open project failed', detail: error instanceof Error ? error.message : 'Could not open project.' });
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

  const newChat = () => {
    setMessages([]);
    setPrompt('');
    addEvent({ kind: 'start', message: 'New chat started', detail: 'Current project files remain in context.' });
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
      await loadRollbackSnapshots(session.id);
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
      } catch {
        // Git metadata is optional for early workspaces.
      }
    } catch {
      localStorage.removeItem('nexus.code.session_id');
      setSessionId('');
      setPatchPreview([]);
      setAnalysis(null);
      setRollbackSnapshots([]);
      setCommands([]);
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
      addEvent({ kind: 'error', message: 'Cancel job failed', detail: error instanceof Error ? error.message : 'Could not cancel job.' });
    }
  };

  const retryJob = async (jobId: string) => {
    if (busy) return;
    try {
      const result = await apiRequest(`/api/v1/code/jobs/${jobId}/retry`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((item) => item.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'code', message: 'Background job retried', detail: result.job?.prompt || jobId });
    } catch (error) {
      addEvent({ kind: 'error', message: 'Retry job failed', detail: error instanceof Error ? error.message : 'Could not retry job.' });
    }
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
    loadProjects();
    loadFiles();
    const savedSessionId = localStorage.getItem('nexus.code.session_id');
    if (savedSessionId) {
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
    const hasRunningJob = jobs.some((job) => ['running', 'queued'].includes(job.status));
    if (!hasRunningJob) return;
    const timer = window.setInterval(() => {
      void refreshJobs(sessionId);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [jobs, sessionId]);

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
      addEvent({ kind: 'error', message: 'Upload failed', detail: error instanceof Error ? error.message : 'Unknown upload error.' });
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
    const session = await apiRequest('/api/v1/code/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: 'NEXUS Code unified workspace', file_ids: selectedFileIds, project_id: projectId || undefined }),
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
      const nextFile = { id: data.id, filename: data.filename, content: data.content || '', dirty: false };
      setOpenTabs((current) => {
        const exists = current.some((item) => item.id === nextFile.id);
        return exists ? current.map((item) => item.id === nextFile.id ? { ...nextFile, dirty: item.dirty, content: item.dirty ? item.content : nextFile.content } : item) : [...current, nextFile];
      });
      setActiveFileId(nextFile.id);
      addEvent({ kind: 'read', message: `Opened ${data.filename}`, detail: 'Loaded into the inline editor.' });
    } catch (error) {
      addEvent({ kind: 'error', message: 'Open file failed', detail: error instanceof Error ? error.message : 'Could not open file.' });
    } finally {
      setBusy(false);
    }
  };

  const searchWorkspace = async () => {
    const query = searchQuery.trim();
    if (!query || busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/search?q=${encodeURIComponent(query)}`);
      setSearchMatches(result.matches || []);
      addEvent({ kind: 'read', message: 'Workspace search complete', detail: `${result.matches?.length || 0} match(es) for "${query}".` });
      await hydrateSession(sid);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Workspace search failed', detail: error instanceof Error ? error.message : 'Could not search files.' });
    } finally {
      setBusy(false);
    }
  };

  const saveOpenFile = async () => {
    if (!openFile || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/files/${openFile.id}/content`, {
        method: 'PUT',
        body: JSON.stringify({ content: openFile.content }),
      });
      updateOpenTab(openFile.id, (file) => ({ ...file, dirty: false }));
      addEvent({ kind: 'done', message: `Saved ${result.filename}`, detail: `${result.size_bytes} bytes written to workspace storage.` });
      await loadFiles();
      if (sessionId) {
        await hydrateSession(sessionId);
      }
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Save failed', detail: error instanceof Error ? error.message : 'Could not save file.' });
    } finally {
      setBusy(false);
    }
  };

  const inlineEditSelection = async (instruction: string, selectedText: string, start: number, end: number) => {
    if (!openFile || busy) return;
    if (!selectedText.trim()) {
      addEvent({ kind: 'error', message: 'Inline edit needs a selection', detail: 'Select the code you want NEXUS to rewrite.' });
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
      addEvent({ kind: 'error', message: 'Inline edit failed', detail: error instanceof Error ? error.message : 'Could not edit selection.' });
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
      addEvent({ kind: 'error', message: 'Completion failed', detail: error instanceof Error ? error.message : 'Could not complete code.' });
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

  const runWorkspace = async () => {
    const instruction = prompt.trim();
    if (!instruction || busy) return;
    setBusy(true);
    setPatchReady(false);
    addMessage('user', instruction);
    setPrompt('');
    await fetchActivityPlan(instruction, mode);
    const modes = inferModes(instruction, mode);
    const outputs: string[] = [];

    try {
      if (selectedFileIds.length) {
        addEvent({ kind: 'read', message: `Reading ${selectedFileIds.length} selected file${selectedFileIds.length === 1 ? '' : 's'}`, detail: 'File context is injected into every hidden agent call.' });
      }

      if (modes.includes('research')) {
        addEvent({ kind: 'research', message: 'Research agent running', detail: 'Gathering relevant web context.' });
        const result = await apiRequest('/api/v1/internet/research', {
          method: 'POST',
          body: JSON.stringify({ query: instruction, depth: 'standard' }),
        });
        outputs.push(result.report || JSON.stringify(result, null, 2));
        addEvent({ kind: 'done', message: 'Research complete' });
      }

      if (modes.includes('design')) {
        addEvent({ kind: 'design', message: 'Design agent running', detail: 'Generating implementation-ready UI guidance.' });
        const result = await apiRequest('/api/v1/design/generate-ui', {
          method: 'POST',
          body: JSON.stringify({ description: instruction, output_type: 'ui', ...model }),
        });
        outputs.push(result.content || JSON.stringify(result, null, 2));
        addEvent({ kind: 'done', message: 'Design generated' });
      }

      if (modes.includes('deploy')) {
        addEvent({ kind: 'deploy', message: 'Deploy agent analyzing', detail: 'No production deploy is triggered without explicit approval.' });
        const result = await apiRequest('/api/v1/deploy/analyze', {
          method: 'POST',
          body: JSON.stringify({ project_type: 'NEXUS Code workspace', repo_context: instruction }),
        });
        outputs.push(`Deployment analysis:\n${JSON.stringify(result, null, 2)}`);
        addEvent({ kind: 'done', message: 'Deploy analysis ready' });
      }

      if (modes.includes('code') || modes.includes('plan')) {
        const sid = await ensureSession();
        addEvent({ kind: 'code', message: 'Planning code changes', detail: 'Generating a concise implementation plan.' });
        const plan = await apiRequest(`/api/v1/code/sessions/${sid}/plan`, {
          method: 'POST',
          body: JSON.stringify({ instruction, ...model }),
        });
        if (plan.job) setJobs((current) => [plan.job, ...current.filter((job) => job.id !== plan.job.id)].slice(0, 20));
        outputs.push(`Implementation plan:\n${plan.plan}`);
        if (modes.includes('code')) {
          addEvent({ kind: 'edit', message: 'Preparing patch', detail: 'Patch is generated but not applied until you approve it.' });
          const patch = await apiRequest(`/api/v1/code/sessions/${sid}/patch`, {
            method: 'POST',
            body: JSON.stringify({ instruction, ...model }),
          });
          if (patch.job) setJobs((current) => [patch.job, ...current.filter((job) => job.id !== patch.job.id)].slice(0, 20));
          const preview = patch.patch_preview || [];
          setPatchPreview(preview);
          setPatchReady(true);
          if (preview.length) {
            preview.forEach((item: any) => {
              addEvent({
                kind: 'edit',
                message: `Patch ready: ${item.filename}`,
                detail: `+${item.additions || 0} / -${item.deletions || 0}`,
                diff: item.diff,
              });
            });
            outputs.push(`Patch prepared. Review the Activity / Changes panel, then approve to apply.\n\n${summarizePreview(preview)}`);
          } else {
            addEvent({ kind: 'edit', message: 'Patch ready for review', detail: summarizePatch(patch.patch), diff: patch.patch });
            outputs.push(`Patch prepared. Review the Activity / Changes panel, then approve to apply.\n\n${summarizePatch(patch.patch)}`);
          }
        }
      }

      addMessage('assistant', outputs.join('\n\n---\n\n') || 'Done.');
      addEvent({ kind: 'done', message: 'NEXUS Code finished', detail: modes.join(', ') });
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Workspace run failed.';
      addEvent({ kind: 'error', message: 'Run failed', detail });
      addMessage('assistant', `I hit an error while running the workspace agents:\n\n${detail}`);
    } finally {
      setBusy(false);
    }
  };

  const runWorkspaceBackground = async () => {
    const instruction = prompt.trim();
    if (!instruction || busy) return;
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
        body: JSON.stringify({ instruction, mode: backgroundMode, ...model }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addMessage('assistant', `Background ${backgroundMode} job started. Track it in Activity / Jobs; pending patches will appear in Changes when ready.`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Could not start background job.';
      addEvent({ kind: 'error', message: 'Background job failed to start', detail });
      addMessage('assistant', `I could not start the background job:\n\n${detail}`);
    } finally {
      setBusy(false);
    }
  };

  const applyChanges = async () => {
    if (!sessionId || !patchReady || busy) return;
    setBusy(true);
    try {
      addEvent({ kind: 'edit', message: 'Applying approved patch', detail: 'Writing changes into app-managed workspace files.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      setPatchPreview(result.remaining || []);
      const changed = result.changed || [];
      changed.forEach((item: any) => {
        addEvent({ kind: 'edit', message: `Edited ${item.filename}`, detail: `${item.diff?.split('\n').length || 0} diff lines`, diff: item.diff });
      });
      setPatchReady(false);
      addMessage('assistant', `Applied ${changed.length} file${changed.length === 1 ? '' : 's'}.\n${result.summary || ''}`.trim());
      await loadFiles();
      if (sessionId) {
        await hydrateSession(sessionId);
      }
    } catch (error) {
      addEvent({ kind: 'error', message: 'Apply failed', detail: error instanceof Error ? error.message : 'Could not apply patch.' });
    } finally {
      setBusy(false);
    }
  };

  const applyFileChange = async (fileId: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ file_ids: [fileId] }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      const remaining = result.remaining || [];
      setPatchPreview(remaining);
      setPatchReady(Boolean(remaining.length));
      (result.changed || []).forEach((item: any) => {
        addEvent({ kind: 'edit', message: `Applied ${item.filename}`, detail: `${item.diff?.split('\n').length || 0} diff lines`, diff: item.diff });
      });
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Apply file failed', detail: error instanceof Error ? error.message : 'Could not apply selected file.' });
    } finally {
      setBusy(false);
    }
  };

  const runCommand = async (command: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: `Running ${command}`, detail: 'Executing in an isolated temporary workspace from selected files.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/run-command`, {
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
    } catch (error) {
      addEvent({ kind: 'error', message: 'Command failed', detail: error instanceof Error ? error.message : 'Could not run command.' });
    } finally {
      setBusy(false);
    }
  };

  const runChecks = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const sid = await ensureSession();
      addEvent({ kind: 'deploy', message: 'Running workspace checks', detail: 'NEXUS will run detected safe build/test/lint/typecheck commands.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sid}/run-checks`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: result.status === 'passed' ? 'done' : 'error',
        message: `Workspace checks ${result.status}`,
        detail: `${result.passed || 0}/${result.total || 0} check(s) passed.`,
      });
      await hydrateSession(sid);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Workspace checks failed', detail: error instanceof Error ? error.message : 'Could not run workspace checks.' });
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
    } catch (error) {
      addEvent({ kind: 'error', message: 'Runtime sync failed', detail: error instanceof Error ? error.message : 'Could not sync runtime workspace.' });
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
      addEvent({ kind: 'error', message: 'Workspace analysis failed', detail: error instanceof Error ? error.message : 'Could not analyze workspace.' });
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
      ].filter(Boolean).join('\n');
      addEvent({ kind: result.status === 'passed' ? 'done' : 'error', message: `Preview check ${result.status}`, detail });
      setPreviewChecks((current) => [...current, result].slice(-30));
      await hydrateSession(sid);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Preview check failed', detail: error instanceof Error ? error.message : 'Could not check preview.' });
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
      addEvent({ kind: 'error', message: 'Live preview failed', detail: error instanceof Error ? error.message : 'Could not start live preview.' });
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
      addEvent({ kind: 'error', message: 'Stop preview failed', detail: error instanceof Error ? error.message : 'Could not stop live preview.' });
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
      addEvent({ kind: 'error', message: 'Preview logs unavailable', detail: error instanceof Error ? error.message : 'Could not load preview logs.' });
    } finally {
      setBusy(false);
    }
  };

  const fixPreviewIssue = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      addEvent({ kind: 'edit', message: 'Fixing preview issue', detail: 'Using the latest preview check to prepare a patch.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/fix-preview`, {
        method: 'POST',
        body: JSON.stringify({ instruction: 'Prepare the smallest safe code change that fixes the preview failure.', ...model }),
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
      addMessage('assistant', `Preview fix prepared. Review the patch in Activity, then approve to apply.\n\n${summarizePreview(preview)}`);
      await hydrateSession(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Fix preview failed', detail: error instanceof Error ? error.message : 'Could not prepare preview fix.' });
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
      addEvent({ kind: 'error', message: 'Repository connect failed', detail: error instanceof Error ? error.message : 'Could not connect repository.' });
    } finally {
      setBusy(false);
    }
  };

  const importRepo = async () => {
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
      addEvent({ kind: 'error', message: 'GitHub import failed', detail: error instanceof Error ? error.message : 'Could not import repository.' });
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
        body: JSON.stringify({ title: 'NEXUS Code workspace changes' }),
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({
        kind: 'done',
        message: 'Pull request plan prepared',
        detail: `Branch: ${result.branch_name}\nCommit: ${result.commit_message}\n\n${result.pr_body}`,
      });
      await hydrateSession(sid);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Prepare PR failed', detail: error instanceof Error ? error.message : 'Could not prepare PR.' });
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
      addEvent({ kind: 'error', message: 'Open PR failed', detail: error instanceof Error ? error.message : 'Could not open GitHub PR.' });
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
        addEvent({ kind: 'error', message: 'Reject failed', detail: 'Could not clear the pending patch on the server.' });
      }
    }
    setPatchReady(false);
    setPatchPreview([]);
    addEvent({ kind: 'done', message: 'Changes rejected', detail: 'Prepared patch was discarded from the UI approval flow.' });
  };

  const rejectFileChange = async (fileId: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ file_ids: [fileId] }),
      });
      const remaining = result.remaining || [];
      setPatchPreview(remaining);
      setPatchReady(Boolean(remaining.length));
      addEvent({ kind: 'done', message: 'File change rejected', detail: `${result.rejected?.length || 0} file(s) removed from pending changes.` });
      await hydrateSession(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Reject file failed', detail: error instanceof Error ? error.message : 'Could not reject selected file.' });
    } finally {
      setBusy(false);
    }
  };

  const rollbackChanges = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/rollback`, { method: 'POST' });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'done', message: 'Rolled back last apply', detail: `${result.restored?.length || 0} file(s) restored.` });
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Rollback failed', detail: error instanceof Error ? error.message : 'Could not rollback changes.' });
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
      await loadFiles();
      await hydrateSession(sessionId);
      await loadRollbackSnapshots(sessionId);
    } catch (error) {
      addEvent({ kind: 'error', message: 'Rollback snapshot failed', detail: error instanceof Error ? error.message : 'Could not restore selected snapshot.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <DesktopOnlyGuard product="NEXUS Code" reason="NEXUS Code is optimized for desktop workspaces with files, editor, terminal-style actions, preview, diffs, jobs, and Git controls.">
      <main className={styles.workspace}>
      <WorkspaceSidebar
        recentItems={recentItems}
        busy={busy}
        onCreateProject={createProject}
        onNewChat={newChat}
        onSearch={focusWorkspaceSearch}
        onOpenRecent={openRecent}
      />
      <header className={styles.topbar}>
        <input
          className={styles.search}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onFocus={focusWorkspaceSearch}
          onKeyDown={(event) => {
            if (event.key === 'Enter') searchWorkspace();
          }}
          placeholder="Search files, commands, agents..."
        />
        <div className={styles.topActions}>
          <span className={styles.projectBadge}>{activeProject?.name || 'No project'}</span>
          <MoreHorizontal size={18} />
          <UserCircle size={22} />
        </div>
      </header>
      <div className={styles.layout}>
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
        />
        <ConversationPanel
          mode={mode}
          messages={messages}
          prompt={prompt}
          busy={busy}
          selectedFileCount={selectedFileIds.length}
          onModeChange={setMode}
          onPromptChange={setPrompt}
          onSubmit={runWorkspace}
          onSubmitBackground={runWorkspaceBackground}
          onAttachClick={() => fileInputRef.current?.click()}
        />
        <ActivityPanel
          events={events}
          jobs={jobs}
          patchPreview={patchPreview}
          commands={commands}
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
          canUseGit={Boolean(repoUrl.trim()) && !busy}
          onApply={applyChanges}
          onReject={rejectChanges}
          onApplyFile={applyFileChange}
          onRejectFile={rejectFileChange}
          onRollback={rollbackChanges}
          onRollbackSnapshot={rollbackSnapshot}
          onLoadRollbackSnapshots={() => loadRollbackSnapshots()}
          onRunCommand={runCommand}
          onRunChecks={runChecks}
          onRefreshJobs={refreshCurrentJobs}
          onCancelJob={cancelJob}
          onRetryJob={retryJob}
          onSyncRuntime={syncRuntime}
          onAnalyzeWorkspace={analyzeWorkspace}
          onPreviewUrlChange={setPreviewUrl}
          onCheckPreview={checkPreview}
          onFixPreview={fixPreviewIssue}
          onStartPreview={startLivePreview}
          onStopPreview={stopLivePreview}
          onLoadPreviewLogs={loadPreviewLogs}
          onRepoUrlChange={setRepoUrl}
          onConnectRepo={connectRepo}
          onImportRepo={importRepo}
          onPreparePr={preparePr}
          onOpenPr={openPr}
        />
      </div>
      {filesOpen && (
        <div className={styles.filesDrawerBackdrop} role="presentation" onMouseDown={() => setFilesOpen(false)}>
          <div className={styles.filesDrawer} role="dialog" aria-label="Project files" onMouseDown={(event) => event.stopPropagation()}>
            <div className={styles.drawerHeader}>
              <span>Project Files</span>
              <button type="button" onClick={() => setFilesOpen(false)}>Close</button>
            </div>
            <FileExplorer
              files={files}
              selectedIds={selectedFileIds}
              searchQuery={searchQuery}
              searchMatches={searchMatches}
              busy={busy}
              onRefresh={loadFiles}
              onToggleFile={(fileId) => setSelected((current) => ({ ...current, [fileId]: !current[fileId] }))}
              onOpenFile={(file) => {
                openWorkspaceFile(file);
                setFilesOpen(false);
              }}
              onSearchChange={setSearchQuery}
              onSearch={searchWorkspace}
              onUpload={uploadFiles}
              searchFocusKey={searchFocusKey}
            />
          </div>
        </div>
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
