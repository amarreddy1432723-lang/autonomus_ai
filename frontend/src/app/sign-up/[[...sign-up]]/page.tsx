'use client';

import { FormEvent, Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowRight, Sparkles } from 'lucide-react';
import { apiRequest } from '../../../utils/api';
import { writeDesktopAuthState } from '../../../utils/desktopAuth';

function normalizeRedirect(value: string | null): string {
  if (!value || !value.startsWith('/')) return '/workspace';
  return value;
}

function SignUpPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectUrl = normalizeRedirect(searchParams.get('redirect_url'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await apiRequest('/api/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      const tokens = await apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      writeDesktopAuthState(tokens);
      const user = await apiRequest('/api/v1/auth/me');
      writeDesktopAuthState({ ...tokens, user_id: user.id });
      router.push(redirectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign up failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: '#f7f8fa', color: '#1b1b1f' }}>
      <section style={{ width: 'min(430px, 100%)', border: '1px solid #ececec', borderRadius: 16, padding: 28, background: '#ffffff', boxShadow: '0 24px 70px rgba(17, 24, 39, 0.08)' }}>
        <div style={{ width: 42, height: 42, display: 'grid', placeItems: 'center', borderRadius: 12, background: 'linear-gradient(135deg, #7b61ff, #5ba7ff)', color: '#ffffff', marginBottom: 18 }}>
          <Sparkles size={20} />
        </div>
        <h1 style={{ fontSize: 28, lineHeight: 1.15, margin: '0 0 8px' }}>Create your Arceus account</h1>
        <p style={{ margin: '0 0 22px', color: '#5d6472', lineHeight: 1.55 }}>Start with first-party Arceus authentication. You can connect SSO later when the product is ready for enterprise rollout.</p>
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
          <label style={{ display: 'grid', gap: 7, fontSize: 13, fontWeight: 750 }}>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              style={{ height: 42, border: '1px solid #ececec', borderRadius: 10, padding: '0 12px', fontSize: 14 }}
            />
          </label>
          <label style={{ display: 'grid', gap: 7, fontSize: 13, fontWeight: 750 }}>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={12}
              required
              style={{ height: 42, border: '1px solid #ececec', borderRadius: 10, padding: '0 12px', fontSize: 14 }}
            />
          </label>
          <p style={{ margin: '-4px 0 0', color: '#7b8190', fontSize: 12 }}>Use at least 12 characters.</p>
          {error && <div style={{ border: '1px solid #fecaca', background: '#fff1f2', color: '#b91c1c', borderRadius: 10, padding: 11, fontSize: 13 }}>{error}</div>}
          <button
            type="submit"
            disabled={submitting}
            style={{ height: 44, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, border: 0, borderRadius: 10, background: '#5f34e8', color: '#ffffff', fontWeight: 850, cursor: submitting ? 'wait' : 'pointer', opacity: submitting ? 0.72 : 1 }}
          >
            {submitting ? 'Creating account...' : 'Create account'}
            <ArrowRight size={16} />
          </button>
        </form>
        <p style={{ margin: '18px 0 0', color: '#5d6472', fontSize: 13 }}>
          Already have an account?{' '}
          <Link href={`/sign-in?redirect_url=${encodeURIComponent(redirectUrl)}`} style={{ color: '#5f34e8', fontWeight: 800, textDecoration: 'none' }}>Sign in</Link>
        </p>
      </section>
    </main>
  );
}

export default function SignUpPage() {
  return (
    <Suspense fallback={null}>
      <SignUpPageContent />
    </Suspense>
  );
}
