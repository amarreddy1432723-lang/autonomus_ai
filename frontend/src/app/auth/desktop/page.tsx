'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { MonitorCheck } from 'lucide-react';
import { apiRequest } from '../../../utils/api';

export default function DesktopAuthPage() {
  const [status, setStatus] = useState('Preparing desktop sign-in...');
  const [error, setError] = useState('');
  const [needsSignIn, setNeedsSignIn] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        setStatus('Creating secure desktop handoff...');
        const clerk = (window as any).Clerk;
        const clerkToken = clerk?.session?.getToken ? await clerk.session.getToken() : null;
        let result;
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
  }, []);

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
          <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
            <Link href="/sign-in?redirect_url=/auth/desktop" style={{ color: '#c4b5fd', fontWeight: 800 }}>Sign in</Link>
            <Link href="/signup" style={{ color: '#a1a1aa' }}>Create account</Link>
          </div>
        )}
      </section>
    </main>
  );
}
