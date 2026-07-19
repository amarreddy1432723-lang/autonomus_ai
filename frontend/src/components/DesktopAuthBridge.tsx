'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiRequest } from '../utils/api';
import { writeDesktopAuthState } from '../utils/desktopAuth';

export default function DesktopAuthBridge() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window === 'undefined' || !window.electron?.onAuthCode) return;
    const unsubscribe = window.electron.onAuthCode(async ({ code }) => {
      if (!code) return;
      try {
        const token = await apiRequest('/api/v1/auth/desktop/exchange', {
          method: 'POST',
          body: JSON.stringify({ code }),
        });
        writeDesktopAuthState(token);
        const me = await apiRequest('/api/v1/auth/me');
        if (me?.id) {
          writeDesktopAuthState({ id: me.id });
        }
        router.push('/workspace');
      } catch (error) {
        console.error('Desktop auth exchange failed', error);
      }
    });
    return unsubscribe;
  }, [router]);

  return null;
}
