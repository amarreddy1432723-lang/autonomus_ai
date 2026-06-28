'use client';

import React, { useState } from 'react';
import AppShell from '../../components/AppShell';
import { Settings, Shield, User, Bell, Key, RefreshCw } from 'lucide-react';

export default function SettingsPage() {
  const [autonomy, setAutonomy] = useState(70);

  return (
    <AppShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.5px' }}>
          System Settings
        </h1>

        <div style={{
          display: 'grid',
          gridTemplateColumns: '200px 1fr',
          gap: '32px',
          backgroundColor: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          padding: '24px'
        }}>
          {/* Settings Sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderRight: '1px solid var(--color-border)', paddingRight: '16px' }}>
            <button style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'var(--color-bg-hover)', border: 'none', color: 'var(--color-text-primary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', textAlign: 'left', width: '100%', fontSize: 'var(--text-sm)' }}>
              <Shield size={14} /> Autonomy policy
            </button>
            <button style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', textAlign: 'left', width: '100%', fontSize: 'var(--text-sm)' }}>
              <User size={14} /> Profile settings
            </button>
            <button style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'var(--color-text-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', textAlign: 'left', width: '100%', fontSize: 'var(--text-sm)' }}>
              <Bell size={14} /> Notifications
            </button>
          </div>

          {/* Settings Content Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {/* AUTONOMY SLIDER */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>AI Autonomy Level</h2>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                Set the thresholds at which the AI is permitted to execute plans autonomously.
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '12px' }}>
                <input 
                  type="range" 
                  min="0" 
                  max="100" 
                  value={autonomy} 
                  onChange={(e) => setAutonomy(Number(e.target.value))}
                  style={{ flex: 1, accentColor: 'var(--color-accent-primary)' }}
                />
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{autonomy}%</span>
              </div>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', marginTop: '4px' }}>
                {autonomy > 80 ? '⚠️ High Autonomy: AI will perform code modifications and external requests without manual approvals.' : '🔒 Balanced Autonomy: AI will prompt for approval on high-risk integrations.'}
              </span>
            </div>

            {/* INTEGRATIONS SYNC */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid var(--color-border)', paddingTop: '16px' }}>
              <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Connected Developer Tools</h2>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                backgroundColor: 'var(--color-bg-tertiary)',
                padding: '12px 16px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
                marginTop: '8px'
              }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <div style={{ width: '28px', height: '28px', backgroundColor: '#24292e', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 'bold', fontSize: '14px' }}>G</div>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>GitHub integration</span>
                    <span style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>Status: Active · Connected to 12 repos</span>
                  </div>
                </div>
                <button style={{ backgroundColor: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)', padding: '6px 12px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                  Disconnect
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
