'use client';

import { Suspense } from 'react';
import { SignIn } from '@clerk/nextjs';
import { useRouter, useSearchParams } from 'next/navigation';

function SignInPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get('redirect_url') || '/workspace';

  const handleDemoSignIn = () => {
    // Set cookie for mock authentication
    document.cookie = 'my-ai.mock_token=demo-token; path=/; max-age=86400';
    router.push(redirectUrl);
  };

  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--color-bg-primary)' }}>
        <section style={{ width: 'min(460px, 100%)', border: '1px solid var(--color-border)', borderRadius: 10, padding: 24, background: 'var(--color-bg-secondary)' }}>
          <h1 style={{ fontSize: 24, marginBottom: 8, color: 'var(--color-text-primary)' }}>Login is ready</h1>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: 16 }}>
            Add <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 4px', borderRadius: 4 }}>NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code> in the frontend environment to show the secure Clerk sign-in form here.
          </p>
          <button 
            onClick={handleDemoSignIn}
            style={{
              backgroundColor: 'var(--color-accent-primary)',
              color: 'white',
              border: 'none',
              padding: '12px 20px',
              borderRadius: 6,
              fontWeight: 600,
              cursor: 'pointer',
              width: '100%',
              fontSize: 14
            }}
          >
            Sign in with Demo Account
          </button>
        </section>
      </main>
    );
  }
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--color-bg-primary)' }}>
      <SignIn routing="path" path="/sign-in" signUpUrl={`/sign-up?redirect_url=${encodeURIComponent(redirectUrl)}`} fallbackRedirectUrl={redirectUrl} />
    </main>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInPageContent />
    </Suspense>
  );
}
