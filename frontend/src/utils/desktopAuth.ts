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

export function readDesktopAuthState(): DesktopAuthState {
  if (typeof window === 'undefined') {
    return { accessToken: '', refreshToken: '', userId: '', connected: false };
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

export function writeDesktopAuthState(tokens: { access_token?: string; refresh_token?: string; user_id?: string; id?: string }) {
  if (typeof window === 'undefined') return;
  if (tokens.access_token) window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  if (tokens.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  const userId = tokens.user_id || tokens.id;
  if (userId) window.localStorage.setItem(USER_ID_KEY, userId);
  notifyDesktopAuthChanged();
}

export function clearDesktopAuthState() {
  if (typeof window === 'undefined') return;
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
