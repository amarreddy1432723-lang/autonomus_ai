'use client';

import React, { useEffect, useState } from 'react';
import { Key, Check, X, Shield, Sparkles, ExternalLink, RefreshCw } from 'lucide-react';
import { getStoredApiKeys, saveApiKey } from '../../utils/interviewLLM';

type ApiKeyModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onKeysUpdated?: () => void;
};

export default function ApiKeyModal({ isOpen, onClose, onKeysUpdated }: ApiKeyModalProps) {
  const [groqKey, setGroqKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [savedStatus, setSavedStatus] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      const keys = getStoredApiKeys();
      setGroqKey(keys.groq || '');
      setOpenaiKey(keys.openai || '');
      setGeminiKey(keys.gemini || '');
      setSavedStatus(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    saveApiKey('groq', groqKey);
    saveApiKey('openai', openaiKey);
    saveApiKey('gemini', geminiKey);
    setSavedStatus('Keys saved successfully!');
    if (onKeysUpdated) onKeysUpdated();
    setTimeout(() => {
      setSavedStatus(null);
      onClose();
    }, 800);
  };

  const handleClear = () => {
    saveApiKey('groq', '');
    saveApiKey('openai', '');
    saveApiKey('gemini', '');
    setGroqKey('');
    setOpenaiKey('');
    setGeminiKey('');
    setSavedStatus('Keys cleared. Switched to smart fallback mode.');
    if (onKeysUpdated) onKeysUpdated();
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        style={{
          width: 'min(520px, 100%)',
          backgroundColor: '#11131a',
          border: '1px solid rgba(148, 163, 184, 0.22)',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
          color: '#f8fafc',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'rgba(99, 91, 255, 0.15)',
                border: '1px solid rgba(99, 91, 255, 0.4)',
                display: 'grid',
                placeItems: 'center',
                color: '#a8a1ff',
              }}
            >
              <Key size={18} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>Custom LLM API Keys</h2>
              <p style={{ margin: 0, fontSize: '12px', color: '#94a3b8' }}>
                Optional: Add your own key for direct, ultra-fast streaming
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Groq Key (Recommended) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '13px', fontWeight: 700, color: '#f1f5f9' }}>
                ⚡ Groq API Key <span style={{ color: '#10b981', fontSize: '11px' }}>(Ultra-fast / Free tier available)</span>
              </label>
              <a
                href="https://console.groq.com/keys"
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '11px', color: '#818cf8', display: 'flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
              >
                Get Key <ExternalLink size={11} />
              </a>
            </div>
            <input
              type="password"
              placeholder="gsk_..."
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                backgroundColor: '#0a0c10',
                border: '1px solid rgba(148, 163, 184, 0.25)',
                borderRadius: '6px',
                color: '#f8fafc',
                fontSize: '13px',
                outline: 'none',
              }}
            />
          </div>

          {/* OpenAI Key */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '13px', fontWeight: 700, color: '#f1f5f9' }}>OpenAI API Key (GPT-4o / GPT-4o-mini)</label>
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '11px', color: '#818cf8', display: 'flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
              >
                Get Key <ExternalLink size={11} />
              </a>
            </div>
            <input
              type="password"
              placeholder="sk-..."
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                backgroundColor: '#0a0c10',
                border: '1px solid rgba(148, 163, 184, 0.25)',
                borderRadius: '6px',
                color: '#f8fafc',
                fontSize: '13px',
                outline: 'none',
              }}
            />
          </div>

          {/* Gemini Key */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '13px', fontWeight: 700, color: '#f1f5f9' }}>Google Gemini API Key (Flash / Pro)</label>
              <a
                href="https://aistudio.google.com/app/apikey"
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '11px', color: '#818cf8', display: 'flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
              >
                Get Key <ExternalLink size={11} />
              </a>
            </div>
            <input
              type="password"
              placeholder="AIzaSy..."
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                backgroundColor: '#0a0c10',
                border: '1px solid rgba(148, 163, 184, 0.25)',
                borderRadius: '6px',
                color: '#f8fafc',
                fontSize: '13px',
                outline: 'none',
              }}
            />
          </div>
        </div>

        <div
          style={{
            fontSize: '11px',
            color: '#94a3b8',
            backgroundColor: '#0a0c10',
            border: '1px solid rgba(148, 163, 184, 0.15)',
            borderRadius: '6px',
            padding: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Shield size={14} style={{ color: '#10b981', flexShrink: 0 }} />
          <span>Your keys are stored only in your browser local storage and sent directly to the official LLM provider APIs.</span>
        </div>

        {savedStatus && (
          <div style={{ color: '#10b981', fontSize: '12px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Check size={14} /> {savedStatus}
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={handleClear}
            style={{
              padding: '8px 14px',
              backgroundColor: 'transparent',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              color: '#f87171',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Clear Keys
          </button>
          <button
            type="button"
            onClick={handleSave}
            style={{
              padding: '8px 18px',
              backgroundColor: '#635bff',
              border: '1px solid #635bff',
              color: '#ffffff',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Save & Apply
          </button>
        </div>
      </div>
    </div>
  );
}
