'use client';

import { Suspense } from 'react';
import { SignUp } from '@clerk/nextjs';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

function SignUpPageContent() {
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get('redirect_url') || '/workspace';

  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--color-bg-primary)' }}>
        <section style={{ width: 'min(460px, 100%)', border: '1px solid var(--color-border)', borderRadius: 10, padding: 24, background: 'var(--color-bg-secondary)' }}>
          <h1 style={{ fontSize: 24, marginBottom: 8 }}>Sign up is ready</h1>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: 16 }}>
            Add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY in the frontend environment to show the secure Clerk sign-up form here.
          </p>
          <Link href="/dashboard" style={{ color: 'var(--color-accent-primary)', fontWeight: 700, textDecoration: 'none' }}>
            Back to dashboard
          </Link>
        </section>
      </main>
    );
  }
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--color-bg-primary)' }}>
      <SignUp routing="path" path="/sign-up" signInUrl={`/sign-in?redirect_url=${encodeURIComponent(redirectUrl)}`} fallbackRedirectUrl={redirectUrl} />
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
