'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Check, Clipboard, Code2, FileUp, GitPullRequest, MoreHorizontal, Play, Send, Wand2, X } from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

type UploadedFile = {
  id: string;
  filename: string;
  size_bytes?: number;
};

type Mode = 'quick' | 'plan' | 'design';

type DesignPayload = {
  brief: string;
  style: string;
  code: string;
  notes: string;
  planMode?: boolean;
};

const phaseLabels = ['Understand', 'Plan', 'Generate', 'Review', 'Apply', 'Verify'];

export default function WorkspacePage() {
  const [mode, setMode] = useState<Mode>('quick');
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [showFiles, setShowFiles] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [instruction, setInstruction] = useState('Build the requested feature with clean structure, focused changes, and tests where useful.');
  const [designPayload, setDesignPayload] = useState<DesignPayload | null>(null);
  const [quickOutput, setQuickOutput] = useState('');
  const [plan, setPlan] = useState('');
  const [patch, setPatch] = useState('');
  const [accepted, setAccepted] = useState(true);
  const [applySummary, setApplySummary] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const selectedFileIds = useMemo(() => Object.entries(selected).filter(([, value]) => value).map(([id]) => id), [selected]);

  const loadFiles = async () => {
    try {
      setFiles(await apiRequest('/api/v1/files'));
    } catch {
      setFiles([]);
    }
  };

  useEffect(() => {
    loadFiles();
    const raw = sessionStorage.getItem('design_to_workspace');
    if (raw) {
      try {
        const payload = JSON.parse(raw) as DesignPayload;
        setDesignPayload(payload);
        setMode(payload.planMode ? 'plan' : 'design');
        setInstruction([
          `Implement this selected ${payload.style} design as production-ready frontend code.`,
          `Brief: ${payload.brief}`,
          '',
          'Preview HTML/CSS:',
          payload.code,
          '',
          'Design notes:',
          payload.notes,
        ].join('\n'));
      } catch {
        sessionStorage.removeItem('design_to_workspace');
      }
    }
  }, []);

  const uploadFiles = async (fileList: FileList | null) => {
    if (!fileList) return;
    setBusy('Uploading files');
    try {
      for (const file of Array.from(fileList)) {
        const formData = new FormData();
        formData.append('upload', file);
        await apiRequest('/api/v1/files?owner_type=code_workspace', { method: 'POST', body: formData });
      }
      await loadFiles();
    } finally {
      setBusy('');
    }
  };

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const session = await apiRequest('/api/v1/code/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: 'NEXUS workspace plan', file_ids: selectedFileIds }),
    });
    setSessionId(session.id);
    return session.id;
  };

  const runQuick = async () => {
    setBusy('Generating');
    setError('');
    setQuickOutput('');
    try {
      const data = await apiRequest('/api/v1/code/generate', {
        method: 'POST',
        body: JSON.stringify({ instruction, file_ids: selectedFileIds, llm_provider: 'autonomus', llm_model: 'autonomus-ai-v1' }),
      });
      setQuickOutput(data.content || JSON.stringify(data, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
    } finally {
      setBusy('');
    }
  };

  const runPlan = async () => {
    setBusy('Planning');
    setError('');
    try {
      const id = await ensureSession();
      const data = await apiRequest(`/api/v1/code/sessions/${id}/plan`, {
        method: 'POST',
        body: JSON.stringify({ instruction, llm_provider: 'autonomus', llm_model: 'autonomus-ai-v1' }),
      });
      setPlan(data.plan);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Planning failed');
    } finally {
      setBusy('');
    }
  };

  const runPatch = async () => {
    setBusy('Generating patch');
    setError('');
    try {
      const id = await ensureSession();
      const data = await apiRequest(`/api/v1/code/sessions/${id}/patch`, {
        method: 'POST',
        body: JSON.stringify({ instruction, llm_provider: 'autonomus', llm_model: 'autonomus-ai-v1' }),
      });
      setPatch(data.patch);
      setAccepted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Patch generation failed');
    } finally {
      setBusy('');
    }
  };

  const applyPatch = async () => {
    if (!sessionId || !accepted) return;
    setBusy('Applying');
    setError('');
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, { method: 'POST' });
      const changed = data.changed || [];
      setApplySummary(`Implementation complete. ${changed.length} file${changed.length === 1 ? '' : 's'} modified. ${data.summary || ''}`.trim());
      sessionStorage.setItem('workspace_to_deploy', JSON.stringify({ files_changed: changed.map((item: any) => item.filename), summary: data.summary || '' }));
      await loadFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Apply failed');
    } finally {
      setBusy('');
    }
  };

  const sendPlanStepToChat = () => {
    const payload = ['Help me refine this workspace plan step.', '', plan || instruction].join('\n');
    sessionStorage.setItem('interview_to_chat_prompt', payload);
    window.location.href = '/chat';
  };

  const modeButton = (value: Mode, label: string) => (
    <button type="button" className={`${styles.tabButton} ${mode === value ? styles.tabButtonActive : ''}`} onClick={() => setMode(value)}>
      {label}
    </button>
  );

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.commandPanel}>
          <div className={styles.commandHeader}>
            <div className={styles.inlineActions}>
              {modeButton('quick', 'Quick Generate')}
              {modeButton('plan', 'Plan Mode')}
              {modeButton('design', 'Design to Code')}
            </div>
            <div className={styles.inlineActions}>
              <label className={styles.secondaryButton}>
                <FileUp size={15} />
                Upload
                <input hidden multiple type="file" accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css" onChange={(event) => uploadFiles(event.target.files)} />
              </label>
              <button className={styles.secondaryButton} type="button" onClick={() => setShowFiles((value) => !value)}>Files ({selectedFileIds.length})</button>
              <button className={styles.iconAction} type="button" onClick={() => setShowSettings((value) => !value)} aria-label="Workspace settings">
                <MoreHorizontal size={18} />
              </button>
            </div>
          </div>

          {showSettings && (
            <div className={styles.settingsStrip}>
              <span>Session: {sessionId || 'created when needed'}</span>
              <span>Model: Autonomus AI</span>
            </div>
          )}

          {showFiles && (
            <div className={styles.phaseCard}>
              <div className={styles.phaseHeader}>
                <strong>Workspace files</strong>
                <button className={styles.iconAction} type="button" onClick={() => setShowFiles(false)}><X size={15} /></button>
              </div>
              <div className={styles.phaseList}>
                {files.map((file) => (
                  <label key={file.id} className={styles.toggleLabel}>
                    <input
                      type="checkbox"
                      checked={!!selected[file.id]}
                      onChange={(event) => setSelected((current) => ({ ...current, [file.id]: event.target.checked }))}
                    />
                    {file.filename}
                  </label>
                ))}
                {files.length === 0 && <span className={styles.meta}>No uploaded code files yet.</span>}
              </div>
            </div>
          )}

          <div className={styles.promptRow}>
            <textarea className={styles.largePrompt} value={instruction} onChange={(event) => setInstruction(event.target.value)} />
            {mode === 'quick' && <button className={styles.button} onClick={runQuick} disabled={!!busy}><Wand2 size={16} /> Generate</button>}
            {mode !== 'quick' && <button className={styles.button} onClick={runPlan} disabled={!!busy}><GitPullRequest size={16} /> Plan</button>}
          </div>
          {busy && <span className={styles.meta}>{busy}...</span>}
        </section>

        {mode === 'design' && designPayload && (
          <section className={styles.grid}>
            <iframe className={styles.previewFrame} sandbox="allow-same-origin" srcDoc={designPayload.code} title="Selected design preview" />
            <div className={styles.phaseCard}>
              <h2>{designPayload.style} design selected</h2>
              <p>{designPayload.brief}</p>
              <button className={styles.button} type="button" onClick={runQuick}><Code2 size={16} /> Generate implementation</button>
            </div>
          </section>
        )}

        {mode === 'quick' && quickOutput && (
          <section className={styles.phaseCard}>
            <div className={styles.phaseHeader}>
              <strong>Generated output</strong>
              <div className={styles.inlineActions}>
                <button className={styles.secondaryButton} onClick={() => navigator.clipboard.writeText(quickOutput)}><Clipboard size={15} /> Copy</button>
                <button className={styles.secondaryButton} onClick={sendPlanStepToChat}><Send size={15} /> Chat</button>
              </div>
            </div>
            <pre className={styles.diffView}>{quickOutput}</pre>
          </section>
        )}

        {mode !== 'quick' && (
          <section className={styles.phaseList}>
            <div className={styles.grid}>
              {phaseLabels.map((label, index) => (
                <div className={styles.phaseCard} key={label}>
                  <span className={styles.eyebrow}>Phase {index + 1}</span>
                  <h3>{label}</h3>
                  <p className={styles.meta}>
                    {index === 0 && 'Scope, risks, and needed files are extracted from your instruction.'}
                    {index === 1 && 'Generate a checklist before writing code.'}
                    {index === 2 && 'Create a patch from the accepted plan.'}
                    {index === 3 && 'Accept, reject, or send changes to chat.'}
                    {index === 4 && 'Apply accepted patches to workspace files.'}
                    {index === 5 && 'Summarize changes and prepare deployment handoff.'}
                  </p>
                </div>
              ))}
            </div>

            {plan && (
              <div className={styles.phaseCard}>
                <div className={styles.phaseHeader}>
                  <strong>Implementation plan</strong>
                  <div className={styles.inlineActions}>
                    <button className={styles.secondaryButton} onClick={sendPlanStepToChat}><Send size={15} /> Chat</button>
                    <button className={styles.button} onClick={runPatch}><Wand2 size={16} /> Generate Patch</button>
                  </div>
                </div>
                <pre className={styles.diffView}>{plan}</pre>
              </div>
            )}

            {patch && (
              <div className={styles.phaseCard}>
                <div className={styles.phaseHeader}>
                  <strong>Review patch</strong>
                  <div className={styles.inlineActions}>
                    <button className={styles.secondaryButton} onClick={() => setAccepted(true)}><Check size={15} /> Accept</button>
                    <button className={styles.secondaryButton} onClick={() => setAccepted(false)}><X size={15} /> Reject</button>
                    <button className={styles.button} disabled={!accepted} onClick={applyPatch}><Play size={16} /> Apply</button>
                  </div>
                </div>
                <pre className={styles.diffView}>{patch}</pre>
              </div>
            )}

            {applySummary && <div className={styles.summaryCard}>{applySummary}</div>}
          </section>
        )}

        {error && (
          <details className={styles.phaseCard} open>
            <summary>Error details</summary>
            <p className={styles.meta}>{error}</p>
          </details>
        )}
      </main>
    </AppShell>
  );
}
