'use client';

import React, { useState } from 'react';
import { Play, ClipboardList, HelpCircle, AlertTriangle, ChevronDown, ChevronUp, CheckSquare, Square, Settings, FileCode, Check } from 'lucide-react';

export type NavigatorTask = {
  id: string;
  objective: string;
  recommendedTask: string;
  reason: string;
  risks: string;
  suggestedActions: string[];
  manualSteps: string[];
  automatedPrompt: string;
};

type Props = {
  task: NavigatorTask | null;
  onAutomate: (prompt: string) => void;
};

export default function ProjectNavigator({ task, onAutomate }: Props) {
  const [showManual, setShowManual] = useState(false);
  const [checkedActions, setCheckedActions] = useState<Record<number, boolean>>({});

  if (!task) {
    return (
      <div style={{
        padding: '2rem',
        textAlign: 'center',
        color: '#8B919E',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%'
      }}>
        <ClipboardList size={32} color="#8B919E" style={{ opacity: 0.5 }} />
        <span>No project workspace active or analysis pending. Open a folder to begin.</span>
      </div>
    );
  }

  const toggleAction = (idx: number) => {
    setCheckedActions(prev => ({
      ...prev,
      [idx]: !prev[idx]
    }));
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: '#0F1117',
      borderLeft: '1px solid #1E2535',
      color: '#F0F2F5',
      fontFamily: 'Inter, system-ui, sans-serif',
      overflowY: 'auto'
    }}>
      {/* Panel Header */}
      <div style={{
        padding: '1.25rem 1.5rem',
        borderBottom: '1px solid #1E2535',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <ClipboardList size={18} color="#4F8EF7" />
          <span style={{ fontWeight: '800', fontSize: '0.95rem', letterSpacing: '-0.3px' }}>PROJECT NAVIGATOR</span>
        </div>
        <div style={{
          fontSize: '0.75rem',
          background: 'rgba(0, 208, 132, 0.1)',
          color: '#00D084',
          padding: '0.2rem 0.6rem',
          borderRadius: '4px',
          fontWeight: '700'
        }}>
          ANALYZED
        </div>
      </div>

      <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
        {/* Objective Card */}
        <div style={{
          background: 'rgba(255,255,255,0.01)',
          border: '1px solid #1E2535',
          borderRadius: '10px',
          padding: '1.25rem'
        }}>
          <span style={{ fontSize: '0.75rem', fontWeight: '700', color: '#8B919E', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Current Objective</span>
          <p style={{ marginTop: '0.5rem', fontSize: '1rem', fontWeight: '700', lineHeight: '1.4' }}>{task.objective}</p>
        </div>

        {/* Recommended Task */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: '700', color: '#8B919E', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Recommended Next Task</span>
          <h3 style={{ fontSize: '1.15rem', fontWeight: '900', color: '#4F8EF7', lineHeight: '1.3' }}>{task.recommendedTask}</h3>
        </div>

        {/* Why & Risks Block */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
            <HelpCircle size={16} color="#8B919E" style={{ marginTop: '0.15rem', flexShrink: 0 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: '700', color: '#F0F2F5' }}>Why this is next</span>
              <p style={{ fontSize: '0.85rem', color: '#8B919E', lineHeight: '1.4' }}>{task.reason}</p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
            <AlertTriangle size={16} color="#F5A623" style={{ marginTop: '0.15rem', flexShrink: 0 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: '700', color: '#F5A623' }}>Associated Risk</span>
              <p style={{ fontSize: '0.85rem', color: '#8B919E', lineHeight: '1.4' }}>{task.risks}</p>
            </div>
          </div>
        </div>

        {/* Checklist */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: '700', color: '#8B919E', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Suggested Actions Checklist</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {task.suggestedActions.map((action, idx) => {
              const isChecked = !!checkedActions[idx];
              return (
                <div
                  key={idx}
                  onClick={() => toggleAction(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.75rem',
                    cursor: 'pointer',
                    userSelect: 'none'
                  }}
                >
                  <div style={{ color: isChecked ? '#00D084' : '#8B919E', marginTop: '0.15rem' }}>
                    {isChecked ? <CheckSquare size={16} /> : <Square size={16} />}
                  </div>
                  <span style={{
                    fontSize: '0.85rem',
                    color: isChecked ? '#8B919E' : '#F0F2F5',
                    textDecoration: isChecked ? 'line-through' : 'none',
                    lineHeight: '1.4'
                  }}>
                    {action}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Manual Implementation Collapsible */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <button
            onClick={() => setShowManual(!showManual)}
            style={{
              background: '#161B27',
              border: '1px solid #1E2535',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              color: '#F0F2F5',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontWeight: '700',
              fontSize: '0.85rem'
            }}
          >
            <span>Manual Implementation Guide</span>
            {showManual ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>

          {showManual && (
            <div style={{
              background: '#08090E',
              border: '1px solid #1E2535',
              borderTop: 'none',
              borderBottomLeftRadius: '8px',
              borderBottomRightRadius: '8px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
              marginTop: '-0.50rem'
            }}>
              <ol style={{ paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', color: '#8B919E', fontSize: '0.85rem', lineHeight: '1.5' }}>
                {task.manualSteps.map((step, idx) => (
                  <li key={idx}>
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* Automation Button */}
        <button
          onClick={() => onAutomate(task.automatedPrompt)}
          style={{
            background: '#4F8EF7',
            color: '#08090E',
            border: 'none',
            padding: '1rem',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: '800',
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.75rem',
            boxShadow: '0 4px 15px rgba(79, 142, 247, 0.3)',
            marginTop: '1rem'
          }}
        >
          <Play size={18} fill="#08090E" />
          Let Arceus Implement
        </button>
      </div>
    </div>
  );
}
