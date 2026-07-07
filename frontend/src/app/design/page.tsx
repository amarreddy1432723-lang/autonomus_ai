'use client';

import { useState } from 'react';
import { Clipboard, MoreHorizontal, Send, Sparkles } from 'lucide-react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

type DesignVariant = {
  style: string;
  title: string;
  content: string;
  preview_html: string;
};

export default function DesignPage() {
  const [description, setDescription] = useState('Design a professional dark SaaS dashboard for an AI productivity platform with usage charts and approval queue.');
  const [outputType, setOutputType] = useState('page');
  const [showSettings, setShowSettings] = useState(false);
  const [planMode, setPlanMode] = useState(false);
  const [variants, setVariants] = useState<DesignVariant[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const selected = variants[selectedIndex];

  const generate = async () => {
    setLoading(true);
    setMessage('');
    setVariants([]);
    try {
      const data = await apiRequest('/api/v1/design/variants', {
        method: 'POST',
        body: JSON.stringify({ description, output_type: outputType }),
      });
      setVariants(data.variants || []);
      setSelectedIndex(0);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Design generation failed');
    } finally {
      setLoading(false);
    }
  };

  const implementInWorkspace = () => {
    if (!selected) return;
    sessionStorage.setItem('design_to_workspace', JSON.stringify({
      brief: description,
      style: selected.style,
      code: selected.preview_html,
      notes: selected.content,
      planMode,
    }));
    window.location.href = '/workspace';
  };

  const saveToMemory = async () => {
    if (!selected) return;
    await apiRequest('/api/v1/memories', {
      method: 'POST',
      body: JSON.stringify({
        type: 'design',
        memory_type: 'project_context',
        content: `Selected ${selected.title} for design brief: ${description}`,
        importance: 6,
        confidence: 0.9,
        source: 'design_studio',
        tags: ['design', selected.style],
      }),
    });
    setMessage('Design choice saved to memory');
  };

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.commandPanel}>
          <div className={styles.commandHeader}>
            <div>
              <span className={styles.eyebrow}>Design Brief</span>
              <h1 className={styles.compactTitle}>Generate three UI directions</h1>
            </div>
            <div className={styles.inlineActions}>
              <label className={styles.toggleLabel}>
                <input type="checkbox" checked={planMode} onChange={(event) => setPlanMode(event.target.checked)} />
                Plan Mode
              </label>
              <button className={styles.iconAction} type="button" onClick={() => setShowSettings((value) => !value)} aria-label="Design settings">
                <MoreHorizontal size={18} />
              </button>
            </div>
          </div>

          {showSettings && (
            <div className={styles.settingsStrip}>
              <label>
                Output
                <select className={styles.select} value={outputType} onChange={(event) => setOutputType(event.target.value)}>
                  <option value="page">Full page</option>
                  <option value="ui">Component system</option>
                  <option value="animation">Animation pass</option>
                  <option value="critique">UX critique</option>
                </select>
              </label>
            </div>
          )}

          <div className={styles.promptRow}>
            <textarea
              className={styles.largePrompt}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe what you want designed..."
            />
            <button className={styles.button} disabled={loading || !description.trim()} onClick={generate}>
              <Sparkles size={16} />
              {loading ? 'Generating' : 'Generate'}
            </button>
          </div>
        </section>

        {loading && (
          <section className={styles.grid}>
            {[0, 1, 2].map((item) => <div className={styles.skeletonCard} key={item} />)}
          </section>
        )}

        {variants.length > 0 && (
          <>
            <section className={styles.variantGrid} aria-label="Design variants">
              {variants.map((variant, index) => (
                <button
                  key={variant.style}
                  type="button"
                  className={`${styles.variantCard} ${selectedIndex === index ? styles.variantSelected : ''}`}
                  onClick={() => setSelectedIndex(index)}
                >
                  <div className={styles.variantHeader}>
                    <strong>{variant.title}</strong>
                    <span>{selectedIndex === index ? 'Selected' : 'Click to select'}</span>
                  </div>
                  <iframe className={styles.previewFrame} sandbox="allow-same-origin" srcDoc={variant.preview_html} title={variant.title} />
                </button>
              ))}
            </section>

            <section className={styles.actionBar}>
              <button className={styles.button} onClick={implementInWorkspace}>
                <Send size={16} />
                Implement in Workspace
              </button>
              <button className={styles.secondaryButton} onClick={saveToMemory}>Save to Memory</button>
              <button className={styles.secondaryButton} onClick={() => selected && navigator.clipboard.writeText(selected.preview_html)}>
                <Clipboard size={15} />
                Copy HTML
              </button>
            </section>
          </>
        )}

        {message && <div className={styles.meta}>{message}</div>}
      </main>
    </AppShell>
  );
}
