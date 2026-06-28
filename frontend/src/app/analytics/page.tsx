'use client';

import React, { useState, useEffect } from 'react';
import AppShell from '../../components/AppShell';
import styles from './Analytics.module.css';
import { Lightbulb, AlertTriangle, TrendingUp, BarChart3 } from 'lucide-react';
import { 
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, 
  Tooltip, BarChart, Bar, Legend, Cell 
} from 'recharts';

export default function AnalyticsPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const progressData = [
    { day: 'Jun 15', progress: 10 },
    { day: 'Jun 18', progress: 25 },
    { day: 'Jun 20', progress: 38 },
    { day: 'Jun 22', progress: 45 },
    { day: 'Jun 25', progress: 58 },
    { day: 'Jun 28', progress: 67 }
  ];

  const tasksData = [
    { name: 'Week 1', completed: 8 },
    { name: 'Week 2', completed: 15 },
    { name: 'Week 3', completed: 18 },
    { name: 'Week 4', completed: 23 }
  ];

  const costData = [
    { name: 'GPT-4o', value: 12.10, color: 'var(--color-accent-primary)' },
    { name: 'Embeddings', value: 2.30, color: 'var(--color-accent-secondary)' },
    { name: 'Tools', value: 4.00, color: 'var(--color-agent-memory)' }
  ];

  const insights = [
    { id: '1', text: 'You complete coding tasks 40% faster after lunch hours.', type: 'tip' },
    { id: '2', text: 'Your planning accuracy improved from 54% to 78% this month.', type: 'tip' },
    { id: '3', text: 'Research tasks consistently take 1.3× your initial estimate.', type: 'tip' },
    { id: '4', text: '3 goals are at risk of missing their deadlines — review suggested.', type: 'warning' }
  ];

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>System Analytics</h1>
        </div>

        <div className={styles.grid}>
          {/* GOAL PROGRESS CHART */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span>Goal Progress Over Time</span>
              <span style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>Last 30 Days</span>
            </div>
            <div style={{ flex: 1, minHeight: '220px', width: '100%' }}>
              {mounted && (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={progressData}>
                    <defs>
                      <linearGradient id="colorProgress" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-accent-primary)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--color-accent-primary)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="day" stroke="var(--color-text-tertiary)" fontSize={10} />
                    <YAxis stroke="var(--color-text-tertiary)" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'var(--color-bg-secondary)', 
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text-primary)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px'
                      }} 
                    />
                    <Area 
                      type="monotone" 
                      dataKey="progress" 
                      stroke="var(--color-accent-primary)" 
                      fillOpacity={1} 
                      fill="url(#colorProgress)" 
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* TASK COMPLETION CHART */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span>Tasks Completed per Week</span>
              <span style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>Current Month</span>
            </div>
            <div style={{ flex: 1, minHeight: '220px', width: '100%' }}>
              {mounted && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tasksData}>
                    <XAxis dataKey="name" stroke="var(--color-text-tertiary)" fontSize={10} />
                    <YAxis stroke="var(--color-text-tertiary)" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'var(--color-bg-secondary)', 
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text-primary)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px'
                      }} 
                    />
                    <Bar dataKey="completed" fill="var(--color-accent-secondary)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* AI COST BREAKDOWN CHART */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span>Compute & Token Costs</span>
              <span style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>This Month</span>
            </div>
            <div style={{ flex: 1, minHeight: '220px', width: '100%' }}>
              {mounted && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={costData} layout="vertical">
                    <XAxis type="number" stroke="var(--color-text-tertiary)" fontSize={10} />
                    <YAxis dataKey="name" type="category" stroke="var(--color-text-tertiary)" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'var(--color-bg-secondary)', 
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text-primary)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px'
                      }} 
                    />
                    <Bar dataKey="value" fill="var(--color-accent-primary)" radius={[0, 4, 4, 0]}>
                      {costData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* INSIGHTS */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span>AI Engine Insights</span>
            </div>
            <div className={styles.insightsList}>
              {insights.map((ins) => (
                <div key={ins.id} className={styles.insightItem}>
                  {ins.type === 'warning' ? (
                    <AlertTriangle size={16} className={styles.insightIcon} style={{ color: 'var(--color-error)' }} />
                  ) : (
                    <Lightbulb size={16} className={styles.insightIcon} />
                  )}
                  <span className={styles.insightText}>{ins.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
