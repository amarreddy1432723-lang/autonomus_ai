'use client';

export type ServiceHealthState =
  | 'online'
  | 'agent_offline'
  | 'auth_required'
  | 'partially_online'
  | 'offline_local_only';

export type ServiceHealthSnapshot = {
  state: ServiceHealthState;
  label: string;
  detail: string;
  online: boolean;
  authReady: boolean;
  checkedAt: string;
};

export function isElectronRuntime() {
  return typeof window !== 'undefined' && Boolean((window as any).electron);
}

export function hasDesktopAuthToken() {
  if (typeof window === 'undefined') return false;
  return Boolean(window.localStorage.getItem('my-ai.access_token'));
}

export function serviceHealthCopy(state: ServiceHealthState) {
  switch (state) {
    case 'online':
      return { label: 'Online', detail: 'Agent API and account session are ready.' };
    case 'auth_required':
      return { label: 'Connect account', detail: 'Sign in inside Arceus Code to unlock protected actions.' };
    case 'agent_offline':
      return { label: 'Agent offline', detail: 'Cloud agent API is unreachable. Local folder, editor, and terminal can still work.' };
    case 'offline_local_only':
      return { label: 'Local mode', detail: 'Cloud services are offline. Continue with local files and terminal.' };
    case 'partially_online':
      return { label: 'Partial', detail: 'Some services are reachable, but one or more dependencies need attention.' };
    default:
      return { label: 'Checking', detail: 'Checking service health.' };
  }
}

export async function probeServiceHealth(options: { isSignedIn?: boolean; timeoutMs?: number } = {}): Promise<ServiceHealthSnapshot> {
  const authReady = Boolean(options.isSignedIn || hasDesktopAuthToken());
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? 4500);
  let online = false;
  let dependenciesOk = true;

  try {
    const response = await fetch('/api/v1/ready', {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    online = response.ok;
    if (response.ok) {
      const payload = await response.json().catch(() => null);
      const dependencies = payload?.dependencies;
      dependenciesOk = !dependencies || Object.values(dependencies).every((value) => value === 'ok' || value === true);
    }
  } catch {
    online = false;
  } finally {
    window.clearTimeout(timeout);
  }

  let state: ServiceHealthState;
  if (online && authReady && dependenciesOk) state = 'online';
  else if (online && !authReady) state = 'auth_required';
  else if (online && authReady && !dependenciesOk) state = 'partially_online';
  else state = isElectronRuntime() ? 'offline_local_only' : 'agent_offline';

  const copy = serviceHealthCopy(state);
  return {
    state,
    label: copy.label,
    detail: copy.detail,
    online,
    authReady,
    checkedAt: new Date().toISOString(),
  };
}
