'use client';

import React, { useEffect, useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import { Code2, FileUp, Play, Wand2 } from 'lucide-react';

type UploadedFile = {
  id: string;
  filename: string;
  size_bytes?: number;
  metadata?: { chunk_count?: number };
};

export default function WorkspacePage() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [sessionId, setSessionId] = useState('');
  const [instruction, setInstruction] = useState('Improve this code and fix obvious issues.');
  const [plan, setPlan] = useState('');
  const [patch, setPatch] = useState('');
  const [applyResult, setApplyResult] = useState('');
  const [busy, setBusy] = useState('');

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
    const file_ids = Object.entries(selected).filter(([, value]) => value).map(([id]) => id);
    const session = await apiRequest('/api/v1/code/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: 'Autonomus code workspace', file_ids }),
    });
    setSessionId(session.id);
    return session.id;
  };

  const runPlan = async () => {
    setBusy('Planning');
    try {
      const id = await ensureSession();
      const data = await apiRequest(`/api/v1/code/sessions/${id}/plan`, {
        method: 'POST',
        body: JSON.stringify({ instruction, llm_provider: 'autonomus', llm_model: 'autonomus-ai-v1' }),
      });
      setPlan(data.plan);
    } finally {
      setBusy('');
    }
  };

  const runPatch = async () => {
    setBusy('Generating patch');
    try {
      const id = await ensureSession();
      const data = await apiRequest(`/api/v1/code/sessions/${id}/patch`, {
        method: 'POST',
        body: JSON.stringify({ instruction, llm_provider: 'autonomus', llm_model: 'autonomus-ai-v1' }),
      });
      setPatch(data.patch);
    } finally {
      setBusy('');
    }
  };

  const applyPatch = async () => {
    if (!sessionId) return;
    setBusy('Applying patch');
    try {
      const data = await apiRequest(`/api/v1/code/sessions/${sessionId}/apply`, { method: 'POST' });
      setApplyResult(JSON.stringify(data, null, 2));
      await loadFiles();
    } finally {
      setBusy('');
    }
  };

  return (
    <AppShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800 }}>Code Workspace</h1>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid var(--color-border)', padding: '8px 12px', borderRadius: 6, cursor: 'pointer' }}>
            <FileUp size={16} /> Upload code files
            <input hidden multiple type="file" accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css" onChange={(event) => uploadFiles(event.target.files)} />
          </label>
        </div>

        {busy && <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>{busy}...</span>}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 320px) 1fr', gap: 16 }}>
          <section style={{ border: '1px solid var(--color-border)', borderRadius: 8, padding: 12, background: 'var(--color-bg-secondary)' }}>
            <h2 style={{ fontSize: 'var(--text-sm)', marginBottom: 8 }}>Files</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {files.map((file) => (
                <label key={file.id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-xs)' }}>
                  <input
                    type="checkbox"
                    checked={!!selected[file.id]}
                    onChange={(event) => setSelected((current) => ({ ...current, [file.id]: event.target.checked }))}
                  />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.filename}</span>
                </label>
              ))}
              {files.length === 0 && <span style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>No uploaded files yet.</span>}
            </div>
          </section>

          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              rows={4}
              style={{ width: '100%', background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border)', borderRadius: 8, padding: 12 }}
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button onClick={runPlan} style={{ display: 'inline-flex', gap: 8, alignItems: 'center', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)' }}><Code2 size={16} /> Plan</button>
              <button onClick={runPatch} style={{ display: 'inline-flex', gap: 8, alignItems: 'center', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-accent-primary)', background: 'var(--color-accent-primary)', color: 'white' }}><Wand2 size={16} /> Generate patch</button>
              <button onClick={applyPatch} disabled={!patch} style={{ display: 'inline-flex', gap: 8, alignItems: 'center', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)' }}><Play size={16} /> Apply</button>
            </div>
            {plan && <pre style={{ whiteSpace: 'pre-wrap', border: '1px solid var(--color-border)', borderRadius: 8, padding: 12, background: 'var(--color-bg-secondary)' }}>{plan}</pre>}
            {patch && <pre style={{ whiteSpace: 'pre-wrap', border: '1px solid var(--color-border)', borderRadius: 8, padding: 12, background: 'var(--color-bg-secondary)' }}>{patch}</pre>}
            {applyResult && <pre style={{ whiteSpace: 'pre-wrap', border: '1px solid var(--color-border)', borderRadius: 8, padding: 12, background: 'var(--color-bg-secondary)' }}>{applyResult}</pre>}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
