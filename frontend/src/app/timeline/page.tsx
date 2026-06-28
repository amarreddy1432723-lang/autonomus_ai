'use client';

import React from 'react';
import AppShell from '../../components/AppShell';
import { Hourglass, Cpu, GitCommit, ShieldAlert } from 'lucide-react';

export default function TimelinePage() {
  const events = [
    { time: '09:24 AM', agent: 'Coding Agent', text: 'Fixed 2 failing JWT tests → auth middleware compilation check complete.', type: 'coding' },
    { time: '09:12 AM', agent: 'Coding Agent', text: 'Started implementing auth JWT middleware.', type: 'coding' },
    { time: '09:04 AM', agent: 'Research Agent', text: 'Completed SaaS cloud pricing analysis report.', type: 'research' },
    { time: '09:00 AM', agent: 'Scheduler', text: 'Morning briefing check trigger fired successfully.', type: 'system' }
  ];

  return (
    <AppShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.5px' }}>
          Chronological Audit Timeline
        </h1>

        <div style={{
          backgroundColor: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          {events.map((event, index) => (
            <div key={index} style={{
              display: 'flex',
              gap: '16px',
              position: 'relative',
              paddingBottom: index === events.length - 1 ? '0' : '20px'
            }}>
              {/* Timeline Connector line */}
              {index !== events.length - 1 && (
                <div style={{
                  position: 'absolute',
                  left: '12px',
                  top: '24px',
                  bottom: '0',
                  width: '2px',
                  backgroundColor: 'var(--color-border)'
                }} />
              )}

              {/* Icon indicator */}
              <div style={{
                width: '26px',
                height: '26px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-bg-tertiary)',
                border: '1px solid var(--color-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 2,
                flexShrink: 0
              }}>
                <Cpu size={12} color="var(--color-accent-primary)" />
              </div>

              {/* Text context */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                  {event.time} · {event.agent}
                </span>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', lineHeight: '1.4' }}>
                  {event.text}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
