'use client';

import { useEffect, useMemo, useState } from 'react';
import AppShell from '../../components/AppShell';
import { apiRequest } from '../../utils/api';
import styles from '../nexus.module.css';

type GraphNode = { id: string; label: string; type: string; strength: number };
type GraphEdge = { source: string; target: string; relationship: string; weight: number };

export default function LifeGraphPage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);

  useEffect(() => {
    apiRequest('/api/v1/pa/life-graph')
      .then((data) => {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
      })
      .catch(() => {
        setNodes([]);
        setEdges([]);
      });
  }, []);

  const positioned = useMemo(() => {
    const center = { x: 360, y: 260 };
    return nodes.map((node, index) => {
      if (node.id === 'user') return { ...node, ...center };
      const angle = (index / Math.max(nodes.length - 1, 1)) * Math.PI * 2;
      const radius = 120 + (index % 4) * 28;
      return { ...node, x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius };
    });
  }, [nodes]);

  const byId = new Map(positioned.map((node) => [node.id, node]));

  return (
    <AppShell>
      <main className={styles.page}>
        <section className={styles.commandPanel}>
          <span className={styles.eyebrow}>Shared Intelligence</span>
          <h1 className={styles.compactTitle}>Life Graph</h1>
        </section>
        <section className={styles.graphPanel}>
          <svg viewBox="0 0 720 520" role="img" aria-label="Life graph">
            {edges.map((edge) => {
              const source = byId.get(edge.source);
              const target = byId.get(edge.target);
              if (!source || !target) return null;
              return <line key={`${edge.source}-${edge.target}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="var(--color-border-focus)" strokeOpacity="0.35" strokeWidth={Math.max(1, edge.weight / 3)} />;
            })}
            {positioned.map((node) => (
              <g key={node.id}>
                <circle cx={node.x} cy={node.y} r={node.id === 'user' ? 26 : 12 + node.strength * 8} fill={node.id === 'user' ? 'var(--color-accent-primary)' : 'var(--color-bg-tertiary)'} stroke="var(--color-border-focus)" />
                <text x={node.x + 18} y={node.y + 4} fill="var(--color-text-primary)" fontSize="11">{node.label}</text>
              </g>
            ))}
          </svg>
        </section>
      </main>
    </AppShell>
  );
}
