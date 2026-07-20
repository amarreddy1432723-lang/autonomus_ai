'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Code2 } from 'lucide-react';
import { isElectronRuntime } from '../utils/serviceHealth';

const DESKTOP_CODE_ALLOWED_PREFIXES = [
  '/launch',
  '/workspace',
  '/idea-discovery',
  '/product-intelligence',
  '/domain-intelligence',
  '/product-blueprint',
  '/architecture-strategy',
  '/technology-stack',
  '/engineering-roadmap',
  '/ai-workforce',
  '/executive-review',
  '/mission-control',
  '/evolution-center',
  '/knowledge-graph',
  '/organization-network',
  '/intelligence-kernel',
  '/settings',
  '/auth/desktop',
  '/download',
  '/ui-preview',
];

function isAllowedDesktopCodeRoute(pathname: string) {
  return DESKTOP_CODE_ALLOWED_PREFIXES.some((prefix) => (
    pathname === prefix || pathname.startsWith(`${prefix}/`)
  ));
}

export default function DesktopCodeRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isElectron = isElectronRuntime();
  const allowed = !isElectron || isAllowedDesktopCodeRoute(pathname);

  useEffect(() => {
    if (isElectron && !allowed) {
      router.replace('/launch');
    }
  }, [allowed, isElectron, router]);

  if (!allowed) {
    return (
      <main style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        background: '#07080b',
        color: '#f6f7fb',
        fontFamily: 'var(--font-sans), system-ui, sans-serif',
      }}>
        <section style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
          <Code2 size={28} color="#9b7cff" />
          <strong>Opening Arceus Code workspace...</strong>
          <span style={{ color: '#9aa3b2', fontSize: 13 }}>Desktop routes are scoped to Code.</span>
        </section>
      </main>
    );
  }

  return <>{children}</>;
}
