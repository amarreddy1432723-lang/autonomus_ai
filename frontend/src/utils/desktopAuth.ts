const ACCESS_TOKEN_KEY = 'my-ai.access_token';
const REFRESH_TOKEN_KEY = 'my-ai.refresh_token';
const USER_ID_KEY = 'my-ai.user_id';
const AUTH_CHANGED_EVENT = 'arceus-desktop-auth-changed';

export type DesktopAuthState = {
  accessToken: string;
  refreshToken: string;
  userId: string;
  connected: boolean;
};

let cachedDesktopAuthState: DesktopAuthState | null = null;
let hydratePromise: Promise<DesktopAuthState> | null = null;

function emptyState(): DesktopAuthState {
  return { accessToken: '', refreshToken: '', userId: '', connected: false };
}

function isElectronRuntime(): boolean {
  return typeof window !== 'undefined' && Boolean((window as any).electron?.isDesktop);
}

function mapStoredTokens(tokens: { access_token?: string; refresh_token?: string; user_id?: string; id?: string } = {}): DesktopAuthState {
  const accessToken = tokens.access_token || '';
  const refreshToken = tokens.refresh_token || '';
  const userId = tokens.user_id || tokens.id || '';
  return {
    accessToken,
    refreshToken,
    userId,
    connected: Boolean(accessToken),
  };
}

function clearLegacyLocalStorage() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_ID_KEY);
}

export function readDesktopAuthState(): DesktopAuthState {
  if (typeof window === 'undefined') {
    return emptyState();
  }
  if (isElectronRuntime()) {
    return cachedDesktopAuthState || emptyState();
  }
  const accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY) || '';
  const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY) || '';
  const userId = window.localStorage.getItem(USER_ID_KEY) || '';
  return {
    accessToken,
    refreshToken,
    userId,
    connected: Boolean(accessToken),
  };
}

export async function hydrateDesktopAuthState(): Promise<DesktopAuthState> {
  if (typeof window === 'undefined') return emptyState();
  if (!isElectronRuntime()) return readDesktopAuthState();
  if (hydratePromise) return hydratePromise;
  hydratePromise = (async () => {
    try {
      const result = await (window as any).electron?.desktopAuth?.read?.();
      const payload = result?.ok === false ? {} : (result?.data || result || {});
      cachedDesktopAuthState = mapStoredTokens(payload);
      clearLegacyLocalStorage();
    } catch {
      cachedDesktopAuthState = emptyState();
    } finally {
      hydratePromise = null;
    }
    notifyDesktopAuthChanged();
    return cachedDesktopAuthState || emptyState();
  })();
  return hydratePromise;
}

export function writeDesktopAuthState(tokens: { access_token?: string; refresh_token?: string; user_id?: string; id?: string }) {
  if (typeof window === 'undefined') return;
  if (isElectronRuntime()) {
    cachedDesktopAuthState = mapStoredTokens(tokens);
    clearLegacyLocalStorage();
    void (window as any).electron?.desktopAuth?.write?.({
      access_token: tokens.access_token || cachedDesktopAuthState.accessToken,
      refresh_token: tokens.refresh_token || cachedDesktopAuthState.refreshToken,
      user_id: tokens.user_id || tokens.id || cachedDesktopAuthState.userId,
      token_type: 'bearer',
    });
    notifyDesktopAuthChanged();
    return;
  }
  if (tokens.access_token) window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  if (tokens.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  const userId = tokens.user_id || tokens.id;
  if (userId) window.localStorage.setItem(USER_ID_KEY, userId);
  notifyDesktopAuthChanged();
}

export function clearDesktopAuthState() {
  if (typeof window === 'undefined') return;
  cachedDesktopAuthState = emptyState();
  if (isElectronRuntime()) {
    clearLegacyLocalStorage();
    void (window as any).electron?.desktopAuth?.clear?.();
    notifyDesktopAuthChanged();
    return;
  }
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_ID_KEY);
  notifyDesktopAuthChanged();
}

export function notifyDesktopAuthChanged() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT, { detail: readDesktopAuthState() }));
}

export function onDesktopAuthChanged(callback: (state: DesktopAuthState) => void) {
  if (typeof window === 'undefined') return () => {};
  const listener = () => callback(readDesktopAuthState());
  window.addEventListener(AUTH_CHANGED_EVENT, listener);
  window.addEventListener('storage', listener);
  window.addEventListener('focus', listener);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, listener);
    window.removeEventListener('storage', listener);
    window.removeEventListener('focus', listener);
  };
}
