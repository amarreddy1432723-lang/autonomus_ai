'use client';

import { MoreHorizontal, UserCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest, createApiHeadersAsync } from '../../utils/api';
import ActivityPanel, { ActivityEvent } from './ActivityPanel';
import ConversationPanel, { WorkspaceMessage, WorkspaceMode } from './ConversationPanel';
import FileExplorer, { WorkspaceFile } from './FileExplorer';
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

export default function WorkspacePage() {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [mode, setMode] = useState<WorkspaceMode>('auto');
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [patchReady, setPatchReady] = useState(false);
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

  useEffect(() => {
    loadFiles();
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
      for (const file of Array.from(fileList)) {
        addEvent({ kind: 'read', message: `Uploading ${file.name}`, detail: 'Extracting text and adding it to workspace context.' });
        const formData = new FormData();
        formData.append('upload', file);
        const uploaded = await apiRequest('/api/v1/files?owner_type=code_workspace', { method: 'POST', body: formData });
        setSelected((current) => ({ ...current, [uploaded.id]: true }));
      }
      await loadFiles();
      addEvent({ kind: 'done', message: 'Files ready', detail: 'Uploaded files can now be used by hidden agents.' });
    } catch (error) {
      addEvent({ kind: 'error', message: 'Upload failed', detail: error instanceof Error ? error.message : 'Unknown upload error.' });
    } finally {
      setBusy(false);
    }
  };

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const session = await apiRequest('/api/v1/code/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: 'NEXUS Code unified workspace', file_ids: selectedFileIds }),
    });
    setSessionId(session.id);
    addEvent({ kind: 'start', message: 'Code session created', detail: session.id });
    return session.id;
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
        outputs.push(`Implementation plan:\n${plan.plan}`);
        if (modes.includes('code')) {
          addEvent({ kind: 'edit', message: 'Preparing patch', detail: 'Patch is generated but not applied until you approve it.' });
          const patch = await apiRequest(`/api/v1/code/sessions/${sid}/patch`, {
            method: 'POST',
            body: JSON.stringify({ instruction, ...model }),
          });
          setPatchReady(true);
          addEvent({ kind: 'edit', message: 'Patch ready for review', detail: summarizePatch(patch.patch), diff: patch.patch });
          outputs.push(`Patch prepared. Review the Activity / Changes panel, then approve to apply.\n\n${summarizePatch(patch.patch)}`);
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

  const applyChanges = async () => {
    if (!sessionId || !patchReady || busy) return;
    setBusy(true);
    try {
      addEvent({ kind: 'edit', message: 'Applying approved patch', detail: 'Writing changes into app-managed workspace files.' });
      const result = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, { method: 'POST' });
      const changed = result.changed || [];
      changed.forEach((item: any) => {
        addEvent({ kind: 'edit', message: `Edited ${item.filename}`, detail: `${item.diff?.split('\n').length || 0} diff lines`, diff: item.diff });
      });
      setPatchReady(false);
      addMessage('assistant', `Applied ${changed.length} file${changed.length === 1 ? '' : 's'}.\n${result.summary || ''}`.trim());
      await loadFiles();
    } catch (error) {
      addEvent({ kind: 'error', message: 'Apply failed', detail: error instanceof Error ? error.message : 'Could not apply patch.' });
    } finally {
      setBusy(false);
    }
  };

  const rejectChanges = () => {
    setPatchReady(false);
    addEvent({ kind: 'done', message: 'Changes rejected', detail: 'Prepared patch was discarded from the UI approval flow.' });
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
          busy={busy}
          onRefresh={loadFiles}
          onToggleFile={(fileId) => setSelected((current) => ({ ...current, [fileId]: !current[fileId] }))}
          onUpload={uploadFiles}
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
        <ActivityPanel events={events} hasPatch={patchReady} canApply={patchReady && !!sessionId && !busy} onApply={applyChanges} onReject={rejectChanges} />
      </div>
      <input
        ref={fileInputRef}
        hidden
        multiple
        type="file"
        accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css,.pdf,.docx,.xlsx"
        onChange={(event) => uploadFiles(event.target.files)}
      />
    </main>
  );
}
