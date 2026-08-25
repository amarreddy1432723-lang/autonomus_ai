'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Code2 } from 'lucide-react';
import { isDesktopRouteAllowed } from '../lib/frontendBoundaries';
import { isElectronRuntime } from '../utils/serviceHealth';

export default function DesktopCodeRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isElectron = isElectronRuntime();
  const allowed = !isElectron || isDesktopRouteAllowed(pathname);

  useEffect(() => {
    if (isElectron && !allowed) {
      router.replace('/workspace');
    }
  }, [allowed, isElectron, router]);

  if (!allowed) {
    return (
      <main style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        background: '#f7f7f8',
        color: '#111827',
        fontFamily: 'var(--font-sans), system-ui, sans-serif',
      }}>
        <section style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
          <Code2 size={28} color="#111827" />
          <strong>Opening Arceus Code workspace...</strong>
          <span style={{ color: '#6b7280', fontSize: 13 }}>Desktop routes are scoped to Code.</span>
        </section>
      </main>
    );
  }

  return <>{children}</>;
}
