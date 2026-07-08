'use client';

import { MoreHorizontal, UserCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest, createApiHeadersAsync } from '../../utils/api';
import ActivityPanel, { ActivityEvent, AgentJob, OSContext } from './ActivityPanel';
import ConversationPanel, { WorkspaceMessage, WorkspaceMode } from './ConversationPanel';
import EditorPanel, { OpenWorkspaceFile } from './EditorPanel';
import FileExplorer, { WorkspaceFile, WorkspaceSearchMatch } from './FileExplorer';
import styles from './Workspace.module.css';

const model = { llm_provider: 'nexus', llm_model: 'nexus-code' };

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
  const [osContext, setOsContext] = useState<OSContext | null>(null);
  const [mode, setMode] = useState<WorkspaceMode>('auto');
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [patchReady, setPatchReady] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [openFile, setOpenFile] = useState<OpenWorkspaceFile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMatches, setSearchMatches] = useState<WorkspaceSearchMatch[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedFileIds = useMemo(
    () => Object.entries(selected).filter(([, value]) => value).map(([fileId]) => fileId),
    [selected]
  );

  const addEvent = (event: Omit<ActivityEvent, 'id'>) => {
    setEvents((current) => [{ ...event, id: id('evt') }, ...current].slice(0, 80));
  };

  const addMessage = (role: WorkspaceMessage['role'], content: string) => {
    setMessages((current) => [...current, { id: id(role), role, content }]);
  };

  const loadFiles = async () => {
    try {
      const data = await apiRequest('/api/v1/files');
      setFiles(data);
    } catch {
      setFiles([]);
    }
  };

  const loadOsContext = async () => {
    try {
      const data = await apiRequest('/api/v1/os/context');
      setOsContext(data);
    } catch {
      setOsContext(null);
    }
  };

  const hydrateSession = async (idValue: string) => {
    if (!idValue) return;
    try {
      const session = await apiRequest(`/api/v1/code/sessions/${idValue}`);
      setSessionId(session.id);
      setSelected(Object.fromEntries((session.file_ids || []).map((fileId: string) => [fileId, true])));
      setEvents(normalizeEvents(session.activity_log || []));
      setPatchReady(Boolean(session.patch_preview?.length || session.patch_text));
      const jobData = await apiRequest(`/api/v1/code/jobs?code_session_id=${encodeURIComponent(session.id)}`);
      setJobs(jobData);
      await loadOsContext();
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
    }
  };

  const refreshJobs = async (idValue: string) => {
    if (!idValue) return;
    try {
      const jobData = await apiRequest(`/api/v1/code/jobs?code_session_id=${encodeURIComponent(idValue)}`);
      setJobs(jobData);
    } catch {
      setJobs([]);
    }
  };

  useEffect(() => {
    loadFiles();
    loadOsContext();
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
      }
      addEvent({ kind: 'done', message: 'Files ready', detail: 'Uploaded files can now be used by hidden agents.' });
      await loadOsContext();
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
      body: JSON.stringify({ title: 'NEXUS Code unified workspace', file_ids: selectedFileIds }),
    });
    setSessionId(session.id);
    localStorage.setItem('nexus.code.session_id', session.id);
    addEvent({ kind: 'start', message: 'Code session created', detail: session.id });
    await refreshJobs(session.id);
    return session.id;
  };

  const openWorkspaceFile = async (file: WorkspaceFile) => {
    if (busy) return;
    setBusy(true);
    try {
      const data = await apiRequest(`/api/v1/files/${file.id}/content`);
      setOpenFile({ id: data.id, filename: data.filename, content: data.content || '', dirty: false });
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
      setOpenFile((current) => current ? { ...current, dirty: false } : current);
      addEvent({ kind: 'done', message: `Saved ${result.filename}`, detail: `${result.size_bytes} bytes written to workspace storage.` });
      await loadFiles();
      if (sessionId) {
        await hydrateSession(sessionId);
      }
      await loadOsContext();
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
      setOpenFile((current) => {
        if (!current) return current;
        return {
          ...current,
          content: `${current.content.slice(0, start)}${replacement}${current.content.slice(end)}`,
          dirty: true,
        };
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'edit', message: 'Inline edit applied to editor', detail: 'Review the replacement, then save the file if it looks right.' });
      await loadOsContext();
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
      setOpenFile((current) => {
        if (!current) return current;
        return {
          ...current,
          content: `${current.content.slice(0, cursor)}${completion}${current.content.slice(cursor)}`,
          dirty: true,
        };
      });
      if (result.job) setJobs((current) => [result.job, ...current.filter((job) => job.id !== result.job.id)].slice(0, 20));
      addEvent({ kind: 'edit', message: 'Completion inserted into editor', detail: 'Review the insertion, then save the file if it looks right.' });
      await loadOsContext();
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
      await loadOsContext();
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Workspace run failed.';
      addEvent({ kind: 'error', message: 'Run failed', detail });
      addMessage('assistant', `I hit an error while running the workspace agents:\n\n${detail}`);
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
      await loadOsContext();
    } catch (error) {
      addEvent({ kind: 'error', message: 'Apply failed', detail: error instanceof Error ? error.message : 'Could not apply patch.' });
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
      await loadOsContext();
    } catch (error) {
      addEvent({ kind: 'error', message: 'Command failed', detail: error instanceof Error ? error.message : 'Could not run command.' });
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
      await hydrateSession(sid);
      await loadOsContext();
    } catch (error) {
      addEvent({ kind: 'error', message: 'Preview check failed', detail: error instanceof Error ? error.message : 'Could not check preview.' });
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
      await loadOsContext();
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
      await loadOsContext();
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
      await loadOsContext();
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
      await loadOsContext();
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
    addEvent({ kind: 'done', message: 'Changes rejected', detail: 'Prepared patch was discarded from the UI approval flow.' });
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
      await loadOsContext();
    } catch (error) {
      addEvent({ kind: 'error', message: 'Rollback failed', detail: error instanceof Error ? error.message : 'Could not rollback changes.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={styles.workspace}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.logo}>N</span>
          <span>NEXUS Code</span>
        </div>
        <input className={styles.search} placeholder="Search files, commands, agents..." />
        <div className={styles.topActions}>
          <MoreHorizontal size={18} />
          <UserCircle size={22} />
        </div>
      </header>
      <div className={styles.layout}>
        <FileExplorer
          files={files}
          selectedIds={selectedFileIds}
          searchQuery={searchQuery}
          searchMatches={searchMatches}
          busy={busy}
          onRefresh={loadFiles}
          onToggleFile={(fileId) => setSelected((current) => ({ ...current, [fileId]: !current[fileId] }))}
          onOpenFile={openWorkspaceFile}
          onSearchChange={setSearchQuery}
          onSearch={searchWorkspace}
          onUpload={uploadFiles}
        />
        <EditorPanel
          file={openFile}
          busy={busy}
          onChange={(content) => setOpenFile((current) => current ? { ...current, content, dirty: true } : current)}
          onSave={saveOpenFile}
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
          onAttachClick={() => fileInputRef.current?.click()}
        />
        <ActivityPanel
          events={events}
          jobs={jobs}
          osContext={osContext}
          hasPatch={patchReady}
          canApply={patchReady && !!sessionId && !busy}
          canRunCommand={selectedFileIds.length > 0 && !busy}
          previewUrl={previewUrl}
          canCheckPreview={Boolean(previewUrl.trim()) && !busy}
          canFixPreview={Boolean(sessionId) && !busy}
          repoUrl={repoUrl}
          canUseGit={Boolean(repoUrl.trim()) && !busy}
          onApply={applyChanges}
          onReject={rejectChanges}
          onRollback={rollbackChanges}
          onRunCommand={runCommand}
          onPreviewUrlChange={setPreviewUrl}
          onCheckPreview={checkPreview}
          onFixPreview={fixPreviewIssue}
          onRepoUrlChange={setRepoUrl}
          onConnectRepo={connectRepo}
          onImportRepo={importRepo}
          onPreparePr={preparePr}
          onOpenPr={openPr}
        />
      </div>
      <input
        ref={fileInputRef}
        hidden
        multiple
        type="file"
        accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css,.pdf,.docx,.xlsx,.zip"
        onChange={(event) => uploadFiles(event.target.files)}
      />
    </main>
  );
}
