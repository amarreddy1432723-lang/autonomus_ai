'use client';

import React, { useState } from 'react';
import { ChevronRight, ChevronLeft, Shield, FolderOpen, Play, Cpu, Settings, Lock, Layers } from 'lucide-react';

const Github = ({ size = 18, ...props }: React.SVGProps<SVGSVGElement> & { size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
  </svg>
);

type OnboardingSettings = {
  mode: 'open' | 'clone' | 'create';
  aiModel: 'recommended' | 'reasoning' | 'fast' | 'local';
  permissions: {
    read: boolean;
    write: boolean;
    terminal: boolean;
    dependencies: boolean;
  };
};

type Props = {
  onComplete: (settings: OnboardingSettings) => void;
  onSelectDirectory: () => void;
};

export default function OnboardingWizard({ onComplete, onSelectDirectory }: Props) {
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState<'open' | 'clone' | 'create'>('open');
  const [aiModel, setAiModel] = useState<'recommended' | 'reasoning' | 'fast' | 'local'>('recommended');
  
  const [permissions, setPermissions] = useState({
    read: true,
    write: true,
    terminal: false,
    dependencies: false
  });

  const nextStep = () => setStep((s) => Math.min(s + 1, 5));
  const prevStep = () => setStep((s) => Math.max(s - 1, 1));

  const handleFinish = () => {
    onComplete({
      mode,
      aiModel,
      permissions
    });
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(8, 9, 14, 0.95)',
      backdropFilter: 'blur(12px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <div style={{
        background: '#0F1117',
        border: '1px solid #1E2535',
        borderRadius: '16px',
        width: '560px',
        padding: '2.5rem',
        boxShadow: '0 10px 40px rgba(0,0,0,0.6)',
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem'
      }}>
        {/* Progress Dots */}
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
          {[1, 2, 3, 4, 5].map((s) => (
            <div
              key={s}
              style={{
                width: s === step ? '24px' : '8px',
                height: '8px',
                borderRadius: '99px',
                background: s === step ? '#4F8EF7' : '#1E2535',
                transition: 'all 0.3s ease'
              }}
            />
          ))}
        </div>

        {/* Step 1: Welcome & Select Work Mode */}
        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: '900', letterSpacing: '-1px' }}>Welcome to Arceus Code</h2>
            <p style={{ color: '#8B919E', lineHeight: '1.5' }}>Get started by selecting how you want to load your project workspace.</p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {[
                { id: 'open', title: 'Open Existing Repository', desc: 'Open a local codebase folder from your device.', icon: <FolderOpen size={18} /> },
                { id: 'clone', title: 'Clone from GitHub', desc: 'Connect and clone repository from Git.', icon: <Github size={18} /> },
                { id: 'create', title: 'Create New Project', desc: 'Initialize a clean Next.js/FastAPI workspace template.', icon: <Settings size={18} /> }
              ].map((opt) => {
                const active = mode === opt.id;
                return (
                  <div
                    key={opt.id}
                    onClick={() => setMode(opt.id as any)}
                    style={{
                      background: active ? 'rgba(79, 142, 247, 0.05)' : '#161B27',
                      border: active ? '1px solid #4F8EF7' : '1px solid #1E2535',
                      borderRadius: '10px',
                      padding: '1.25rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '1rem',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    <div style={{ color: active ? '#4F8EF7' : '#8B919E' }}>{opt.icon}</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      <span style={{ fontWeight: '700', fontSize: '0.95rem' }}>{opt.title}</span>
                      <span style={{ color: '#8B919E', fontSize: '0.8rem' }}>{opt.desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {mode === 'open' && (
              <button
                onClick={onSelectDirectory}
                style={{
                  background: '#161B27',
                  border: '1px dashed #4F8EF7',
                  color: '#4F8EF7',
                  padding: '1rem',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: '700',
                  textAlign: 'center',
                  fontSize: '0.9rem'
                }}
              >
                Choose Local Folder...
              </button>
            )}
          </div>
        )}

        {/* Step 2: Connected Services */}
        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: '900', letterSpacing: '-1px' }}>Connect Services</h2>
            <p style={{ color: '#8B919E', lineHeight: '1.5' }}>Integrate with your hosting providers to push code and open pull requests directly.</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{
                background: '#161B27',
                border: '1px solid #1E2535',
                borderRadius: '10px',
                padding: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <Github size={22} color="#F0F2F5" />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    <span style={{ fontWeight: '700', fontSize: '0.95rem' }}>GitHub Integration</span>
                    <span style={{ color: '#8B919E', fontSize: '0.8rem' }}>Required for org repositories.</span>
                  </div>
                </div>
                <button style={{
                  background: '#4F8EF7',
                  color: '#08090E',
                  border: 'none',
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  fontWeight: '700',
                  fontSize: '0.85rem',
                  cursor: 'pointer'
                }}>
                  Connect
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Select AI Configuration */}
        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: '900', letterSpacing: '-1px' }}>AI Model Configuration</h2>
            <p style={{ color: '#8B919E', lineHeight: '1.5' }}>Select the cognitive brain that powers Arceus planning and code generation.</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {[
                { id: 'recommended', title: 'Arceus Recommended', desc: 'Balanced model for planning and writing code.', icon: <Cpu size={18} /> },
                { id: 'reasoning', title: 'Advanced Reasoning Model', desc: 'Slower, deep-reasoning agent for complex architecture refactoring.', icon: <Layers size={18} /> },
                { id: 'fast', title: 'Fast Coding Assistant', desc: 'Quick turnaround model for small syntax modifications.', icon: <Play size={18} /> },
                { id: 'local', title: 'Local Ollama Model', desc: 'Run locally hosted open-source models completely offline.', icon: <Settings size={18} /> }
              ].map((opt) => {
                const active = aiModel === opt.id;
                return (
                  <div
                    key={opt.id}
                    onClick={() => setAiModel(opt.id as any)}
                    style={{
                      background: active ? 'rgba(79, 142, 247, 0.05)' : '#161B27',
                      border: active ? '1px solid #4F8EF7' : '1px solid #1E2535',
                      borderRadius: '10px',
                      padding: '1.25rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '1rem',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    <div style={{ color: active ? '#4F8EF7' : '#8B919E' }}>{opt.icon}</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      <span style={{ fontWeight: '700', fontSize: '0.95rem' }}>{opt.title}</span>
                      <span style={{ color: '#8B919E', fontSize: '0.8rem' }}>{opt.desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Step 4: Permissions Guard */}
        {step === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: '900', letterSpacing: '-1px' }}>Permissions & Safety Gate</h2>
            <p style={{ color: '#8B919E', lineHeight: '1.5' }}>Configure structural safety limits for the autonomous coding agent.</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { key: 'read', title: 'Allow reading files', desc: 'Read file contents, folder structures, and git history.' },
                { key: 'write', title: 'Allow writing changes', desc: 'Prepare and save file modifications directly to workspace.' },
                { key: 'terminal', title: 'Allow terminal commands', desc: 'Run compilers, tests, and build check commands.' },
                { key: 'dependencies', title: 'Allow installing dependencies', desc: 'Auto-run npm install / pip install for missing modules.' }
              ].map((p) => {
                const checked = (permissions as any)[p.key];
                return (
                  <label
                    key={p.key}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '1rem',
                      background: '#161B27',
                      border: '1px solid #1E2535',
                      borderRadius: '10px',
                      padding: '1rem 1.25rem',
                      cursor: 'pointer'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => setPermissions((prev) => ({ ...prev, [p.key]: e.target.checked }))}
                      style={{ marginTop: '0.25rem', cursor: 'pointer' }}
                    />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      <span style={{ fontWeight: '700', fontSize: '0.9rem', color: '#F0F2F5' }}>{p.title}</span>
                      <span style={{ color: '#8B919E', fontSize: '0.75rem' }}>{p.desc}</span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* Step 5: Onboarding Ready */}
        {step === 5 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', textAlign: 'center' }}>
            <div style={{
              background: 'rgba(0, 208, 132, 0.1)',
              border: '1px solid #00D084',
              width: '64px',
              height: '64px',
              borderRadius: '99px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto'
            }}>
              <Shield size={32} color="#00D084" />
            </div>
            <h2 style={{ fontSize: '1.75rem', fontWeight: '900', letterSpacing: '-1px' }}>Onboarding Complete</h2>
            <p style={{ color: '#8B919E', lineHeight: '1.5', maxWidth: '400px', margin: '0 auto' }}>
              Your workspace permissions and AI models are configured. Arceus Code will now inspect your repository structure.
            </p>
          </div>
        )}

        {/* Navigation Buttons */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          borderTop: '1px solid #1E2535',
          paddingTop: '1.5rem',
          marginTop: '1rem'
        }}>
          {step > 1 ? (
            <button
              onClick={prevStep}
              style={{
                background: 'none',
                border: '1px solid #1E2535',
                color: '#8B919E',
                padding: '0.75rem 1.5rem',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '600',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}
            >
              <ChevronLeft size={16} />
              Back
            </button>
          ) : (
            <div />
          )}

          {step < 5 ? (
            <button
              onClick={nextStep}
              style={{
                background: '#4F8EF7',
                color: '#08090E',
                border: 'none',
                padding: '0.75rem 1.8rem',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '800',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}
            >
              Continue
              <ChevronRight size={16} />
            </button>
          ) : (
            <button
              onClick={handleFinish}
              style={{
                background: '#00D084',
                color: '#08090E',
                border: 'none',
                padding: '0.75rem 2.2rem',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '800',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}
            >
              Analyze Workspace
              <Play size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
