'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, MonitorCheck, RefreshCw } from 'lucide-react';
import { apiRequest } from '../../../utils/api';
import { isElectronRuntime } from '../../../utils/serviceHealth';

export default function DesktopAuthPage() {
  const [status, setStatus] = useState('Preparing desktop sign-in...');
  const [error, setError] = useState('');
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [browserUrl, setBrowserUrl] = useState('');
  const [isDesktop, setIsDesktop] = useState(false);

  const signInUrl = useMemo(() => {
    if (typeof window === 'undefined') return '/sign-in?redirect_url=/auth/desktop';
    return `${window.location.origin}/sign-in?redirect_url=${encodeURIComponent('/auth/desktop')}`;
  }, []);

  const openBrowserSignIn = useCallback(async () => {
    setError('');
    setBrowserUrl(signInUrl);
    setNeedsSignIn(true);
    setStatus('Continue sign-in in your browser. Arceus Code will reconnect automatically after approval.');
    try {
      const result = await window.electron?.openExternal?.(signInUrl);
      if (result && !result.ok) {
        setError(result.message || 'Could not open your browser automatically.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open your browser automatically.');
    }
  }, [signInUrl]);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        const desktop = isElectronRuntime();
        setIsDesktop(desktop);
        setStatus('Creating secure desktop handoff...');
        const clerk = (window as any).Clerk;
        const clerkToken = clerk?.session?.getToken ? await clerk.session.getToken() : null;
        let result;
        if (desktop && !clerkToken) {
          await openBrowserSignIn();
          return;
        }
        if (clerk && !clerkToken && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
          setNeedsSignIn(true);
          setStatus('Sign in in the browser to continue to Arceus Code.');
          return;
        }
        if (clerkToken) {
          result = await fetch('/api/v1/auth/desktop/code', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(clerkToken ? { Authorization: `Bearer ${clerkToken}` } : {}),
            },
            body: JSON.stringify({ redirect_uri: 'arceus://auth/callback' }),
          }).then(async (response) => {
            if (!response.ok) throw new Error((await response.json())?.detail || 'Desktop handoff failed');
            return response.json();
          });
        } else {
          result = await apiRequest('/api/v1/auth/desktop/code', {
            method: 'POST',
            body: JSON.stringify({ redirect_uri: 'arceus://auth/callback' }),
          });
        }
        if (!cancelled) {
          setStatus('Opening Arceus Code...');
          window.location.href = result.redirect_url;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Desktop sign-in failed');
          setStatus('Desktop sign-in could not finish.');
        }
      }
    }

    start();
    return () => {
      cancelled = true;
    };
  }, [openBrowserSignIn]);

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: '#08090e', color: '#f5f5f5' }}>
      <section style={{ width: 'min(480px, 100%)', border: '1px solid #26282d', borderRadius: 10, background: '#15161a', padding: 24 }}>
        <MonitorCheck size={28} />
        <h1 style={{ fontSize: 24, margin: '14px 0 8px' }}>Sign in to Arceus Code</h1>
        <p style={{ color: '#a1a1aa', lineHeight: 1.55 }}>{status}</p>
        {error && (
          <div style={{ marginTop: 16, border: '1px solid #7f1d1d', background: '#2a1111', color: '#fecaca', padding: 12, borderRadius: 8 }}>
            {error}
          </div>
        )}
        {needsSignIn && (
          <div style={{ display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
            {isDesktop ? (
              <button
                type="button"
                onClick={openBrowserSignIn}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid #7c6cf0', background: '#7c6cf0', color: 'white', borderRadius: 8, padding: '9px 12px', fontWeight: 800, cursor: 'pointer' }}
              >
                <ExternalLink size={15} />
                Open browser sign-in
              </button>
            ) : (
              <Link href="/sign-in?redirect_url=/auth/desktop" style={{ color: '#c4b5fd', fontWeight: 800 }}>Sign in</Link>
            )}
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid #26282d', background: '#1d1f25', color: '#d4d4d8', borderRadius: 8, padding: '9px 12px', fontWeight: 800, cursor: 'pointer' }}
            >
              <RefreshCw size={15} />
              Retry
            </button>
            {browserUrl && <span style={{ flexBasis: '100%', color: '#71717a', fontSize: 12 }}>Browser URL: {browserUrl}</span>}
          </div>
        )}
      </section>
    </main>
  );
}
