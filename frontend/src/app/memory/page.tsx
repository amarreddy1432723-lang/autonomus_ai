'use client';

import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Memory.module.css';
import { BrainCircuit, Search, Star, Archive, Edit, Plus } from 'lucide-react';

export default function MemoryPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string>('m1');
  const [draftContent, setDraftContent] = useState('');
  const [draftImportance, setDraftImportance] = useState('5');
  const [draftTags, setDraftTags] = useState('');
  const [memoryType, setMemoryType] = useState('');
  const [newMemory, setNewMemory] = useState('');

  const { data: memories } = useQuery({
    queryKey: ['memories-list', search, memoryType],
    queryFn: async () => {
      try {
        // Semantic search or general list
        const typeParam = memoryType ? `&memory_type=${encodeURIComponent(memoryType)}` : '';
        const path = search
          ? `/api/v1/memories/search?query=${encodeURIComponent(search)}${typeParam}`
          : `/api/v1/memories?limit=100${memoryType ? `&memory_type=${encodeURIComponent(memoryType)}` : ''}`;
        return await apiRequest(path);
      } catch {
        return [
          { id: 'm1', content: 'User prefers AWS for SaaS cloud deployment infrastructure.', type: 'preference', importance: 8, confidence: 0.98, created_at: '2026-06-15T09:00:00Z', tags: ['cloud', 'aws', 'infrastructure'] },
          { id: 'm2', content: 'Decided to prioritize React modules over Angular for frontend framework choice.', type: 'decision', importance: 7, confidence: 0.95, created_at: '2026-06-18T10:30:00Z', tags: ['frontend', 'react'] },
          { id: 'm3', content: 'Amar is proficient in Python, TypeScript, and React development.', type: 'fact', importance: 9, confidence: 0.99, created_at: '2026-06-01T08:00:00Z', tags: ['skills', 'developer'] },
          { id: 'm4', content: 'Stripe is the billing system constraint due to multi-currency webhook speed.', type: 'fact', importance: 8, confidence: 0.92, created_at: '2026-06-20T14:15:00Z', tags: ['billing', 'stripe', 'constraint'] }
        ];
      }
    }
  });

  const selectedMemory = memories?.find((m: any) => m.id === selectedId) || memories?.[0];

  useEffect(() => {
    setSearch(new URLSearchParams(window.location.search).get('query') || '');
  }, []);

  useEffect(() => {
    if (!selectedMemory) {
      return;
    }
    setDraftContent(selectedMemory.content || '');
    setDraftImportance(String(selectedMemory.importance ?? 5));
    setDraftTags(Array.isArray(selectedMemory.tags) ? selectedMemory.tags.join(', ') : '');
  }, [selectedMemory]);

  const updateMemoryMutation = useMutation({
    mutationFn: async () => {
      if (!selectedMemory) {
        throw new Error('No memory selected');
      }
      return apiRequest(`/api/v1/memories/${selectedMemory.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          content: draftContent,
          importance: Number(draftImportance),
          tags: draftTags.split(',').map((tag) => tag.trim()).filter(Boolean)
        })
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['memories-list'] });
    }
  });

  const createMemoryMutation = useMutation({
    mutationFn: async () => {
      return apiRequest('/api/v1/memories', {
        method: 'POST',
        body: JSON.stringify({
          content: newMemory,
          type: memoryType || 'fact',
          memory_type: memoryType || 'fact',
          importance: 5,
          confidence: 0.9,
          source: 'user_explicit',
          tags: []
        })
      });
    },
    onSuccess: async (created: any) => {
      setNewMemory('');
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ['memories-list'] });
    }
  });

  const archiveMemoryMutation = useMutation({
    mutationFn: async () => {
      if (!selectedMemory) {
        throw new Error('No memory selected');
      }
      return apiRequest(`/api/v1/memories/${selectedMemory.id}`, {
        method: 'DELETE'
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['memories-list'] });
    }
  });

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>AI Long-term Memory</h1>
        </div>

        {/* SEARCH BAR */}
        <div className={styles.searchSection}>
          <Search size={18} color="var(--color-text-secondary)" style={{ alignSelf: 'center' }} />
          <input 
            type="text" 
            placeholder="Search AI memories semantically..." 
            className={styles.searchInput}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className={styles.typeSelect}
            value={memoryType}
            onChange={(e) => setMemoryType(e.target.value)}
            aria-label="Memory type filter"
          >
            <option value="">All types</option>
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
            <option value="decision">Decision</option>
            <option value="skill">Skill</option>
            <option value="constraint">Constraint</option>
            <option value="goal_context">Goal Context</option>
            <option value="compressed">Compressed</option>
          </select>
          <button className={styles.btnSearch} onClick={() => queryClient.invalidateQueries({ queryKey: ['memories-list'] })}>Search</button>
        </div>

        <div className={styles.createRow}>
          <input
            type="text"
            value={newMemory}
            onChange={(e) => setNewMemory(e.target.value)}
            placeholder="Add an explicit memory..."
            className={styles.createInput}
          />
          <button
            className={styles.btnSearch}
            type="button"
            disabled={!newMemory.trim() || createMemoryMutation.isPending}
            onClick={() => createMemoryMutation.mutate()}
          >
            <Plus size={14} />
            Add
          </button>
        </div>

        {/* GRID LAYOUT */}
        <div className={styles.grid}>
          {/* LEFT: Memory list */}
          <div className={styles.listPanel}>
            {memories?.map((mem: any) => (
              <div 
                key={mem.id} 
                className={`${styles.memoryCard} ${mem.id === selectedId ? styles.memoryCardActive : ''}`}
                onClick={() => setSelectedId(mem.id)}
              >
                <div className={styles.memoryBrief}>
                  <span className={styles.memoryText}>{mem.content.substring(0, 70)}{mem.content.length > 70 ? '...' : ''}</span>
                  <span className={styles.memoryMeta}>
                    {(mem.memory_type || mem.type).toUpperCase()} · {mem.source || 'unknown'} · {new Date(mem.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className={styles.memoryBadges}>
                  {mem.is_superseded && <span className={styles.conflictBadge}>Conflict</span>}
                  <span className={styles.importance}>★ {mem.importance}</span>
                </div>
              </div>
            ))}
          </div>

          {/* RIGHT: Memory Detail */}
          {selectedMemory && (
            <div className={styles.detailPanel}>
              <div className={styles.detailHeader}>
                <span className={styles.detailTitle}>
                  <BrainCircuit size={20} color="var(--color-accent-primary)" />
                  Memory Detail
                </span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Star size={12} fill="var(--color-warning)" color="var(--color-warning)" />
                  Importance: {selectedMemory.importance}
                </span>
              </div>

              <div className={styles.metaGrid}>
                <span>Type: {(selectedMemory.memory_type || selectedMemory.type || 'fact').toUpperCase()}</span>
                <span>Source: {selectedMemory.source || 'unknown'}</span>
                <span>Confidence: {((selectedMemory.confidence || 0) * 100).toFixed(0)}%</span>
                <span>Accessed: {selectedMemory.access_count || 0} times</span>
                <span>Status: {selectedMemory.is_archived ? 'Archived' : selectedMemory.is_superseded ? 'Conflict review' : 'Active'}</span>
                <span>Score: {selectedMemory.score ? selectedMemory.score.toFixed(3) : 'list'}</span>
              </div>

              <div className={styles.detailContent}>
                <p><strong>Content:</strong></p>
                <textarea
                  value={draftContent}
                  onChange={(e) => setDraftContent(e.target.value)}
                  style={{
                    marginTop: '8px',
                    width: '100%',
                    minHeight: '110px',
                    background: 'var(--color-bg-tertiary)',
                    color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Tags:</p>
                <div className={styles.tagRow}>
                  {selectedMemory.tags?.map((t: string) => (
                    <span key={t} className={styles.tag}>#{t}</span>
                ))}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '12px' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                  Importance
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={draftImportance}
                    onChange={(e) => setDraftImportance(e.target.value)}
                    style={{
                      background: 'var(--color-bg-tertiary)',
                      color: 'var(--color-text-primary)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                      padding: '8px 10px'
                    }}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                  Tags
                  <input
                    type="text"
                    value={draftTags}
                    onChange={(e) => setDraftTags(e.target.value)}
                    placeholder="comma, separated, tags"
                    style={{
                      background: 'var(--color-bg-tertiary)',
                      color: 'var(--color-text-primary)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                      padding: '8px 10px'
                    }}
                  />
                </label>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span>Created: {new Date(selectedMemory.created_at).toLocaleString()}</span>
                {selectedMemory.last_accessed_at && <span>Last accessed: {new Date(selectedMemory.last_accessed_at).toLocaleString()}</span>}
                {selectedMemory.related_memory_ids?.length > 0 && <span>Related conflicts: {selectedMemory.related_memory_ids.length}</span>}
              </div>

              <div className={styles.actions}>
                <button className={styles.btnEdit} type="button" onClick={() => updateMemoryMutation.mutate()}>
                  <Edit size={12} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                  Save
                </button>
                <button className={styles.btnArchive} type="button" onClick={() => archiveMemoryMutation.mutate()}>
                  <Archive size={12} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                  Archive
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
