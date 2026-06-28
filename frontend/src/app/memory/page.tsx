'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Memory.module.css';
import { BrainCircuit, Search, Star, Archive, Trash, Edit } from 'lucide-react';

export default function MemoryPage() {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string>('m1');

  const { data: memories } = useQuery({
    queryKey: ['memories-list', search],
    queryFn: async () => {
      try {
        // Semantic search or general list
        const path = search 
          ? `/api/v1/memories/search?query=${encodeURIComponent(search)}` 
          : '/api/v1/memories';
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
          <button className={styles.btnSearch}>Search</button>
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
                  <span className={styles.memoryText}>{mem.content.substring(0, 50)}...</span>
                  <span className={styles.memoryMeta}>{mem.type.toUpperCase()} · {new Date(mem.created_at).toLocaleDateString()}</span>
                </div>
                <span className={styles.importance}>★ {mem.importance}</span>
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

              <div className={styles.detailContent}>
                <p><strong>Content:</strong></p>
                <p style={{ marginTop: '8px', color: 'var(--color-text-primary)' }}>{selectedMemory.content}</p>
              </div>

              <div>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Tags:</p>
                <div className={styles.tagRow}>
                  {selectedMemory.tags?.map((t: string) => (
                    <span key={t} className={styles.tag}>#{t}</span>
                  ))}
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span>Confidence: {(selectedMemory.confidence * 100).toFixed(0)}%</span>
                <span>Created: {new Date(selectedMemory.created_at).toLocaleString()}</span>
              </div>

              <div className={styles.actions}>
                <button className={styles.btnEdit}>
                  <Edit size={12} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                  Edit
                </button>
                <button className={styles.btnArchive}>
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
