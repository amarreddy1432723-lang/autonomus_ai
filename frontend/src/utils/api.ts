
import { clearDesktopAuthState, readDesktopAuthState } from './desktopAuth';

export function getServiceUrl(path: string): string {
  if (typeof window !== 'undefined') {
    const electronBridge = (window as any).electron;
    if (electronBridge?.isDesktop) {
      const localAgentUrl = 'http://127.0.0.1:8003';
      const localGoalsUrl = 'http://127.0.0.1:8002';
      if (
        path.startsWith('/api/v1/goals') ||
        path.startsWith('/api/v1/tasks') ||
        path.startsWith('/api/v1/schedules') ||
        path.startsWith('/api/v1/analytics') ||
        path.startsWith('/api/v1/approvals')
      ) {
        return localGoalsUrl + path;
      }
      if (
        path.startsWith('/api/v1/ready') ||
        path.startsWith('/api/v1/agents') ||
        path.startsWith('/api/v1/models') ||
        path.startsWith('/api/v1/files') ||
        path.startsWith('/api/v1/github') ||
        path.startsWith('/api/v1/usage') ||
        path.startsWith('/api/v1/billing') ||
        path.startsWith('/api/v1/admin') ||
        path.startsWith('/api/v1/plugins') ||
        path.startsWith('/api/v1/code') ||
        path.startsWith('/api/v1/deploy') ||
        path.startsWith('/api/v1/downloads') ||
        path.startsWith('/api/v1/repositories') ||
        path.startsWith('/api/v1/missions') ||
        path.startsWith('/api/v1/intelligence') ||
        path.startsWith('/api/v1/safety') ||
        path.startsWith('/api/v1/jobs') ||
        path.startsWith('/api/v1/os') ||
        path.startsWith('/api/v1/runtime') ||
        path.startsWith('/api/v1/task-runtime') ||
        path.startsWith('/api/v1/platform') ||
        path.startsWith('/api/v1/learning') ||
        path.startsWith('/api/v1/strategy') ||
        path.startsWith('/api/v1/kernel') ||
        path.startsWith('/api/v1/compute') ||
        path.startsWith('/api/v1/graph') ||
        path.startsWith('/api/v1/governance') ||
        path.startsWith('/api/v1/memory') ||
        path.startsWith('/api/v1/research') ||
        path.startsWith('/api/v1/extensions') ||
        path.startsWith('/api/v1/verification-engine') ||
        path.startsWith('/api/v1/federation') ||
        path.startsWith('/api/v1/civilization') ||
        path.startsWith('/api/v1/product') ||
        path.startsWith('/api/v1/automation') ||
        path.startsWith('/api/v1/intents') ||
        path.startsWith('/api/v1/workspace') ||
        path.startsWith('/api/v1/timeline') ||
        path.startsWith('/api/v1/dashboard') ||
        path.startsWith('/api/v1/voice') ||
        path.startsWith('/api/v1/search') ||
        path.startsWith('/api/v1/sessions')
      ) {
        return localAgentUrl + path;
      }
    }
    return path;
  }
  
  const AUTH_URL = process.env.NEXT_PUBLIC_AUTH_URL || 'http://localhost:8001';
  const GOALS_URL = process.env.NEXT_PUBLIC_GOALS_URL || 'http://localhost:8002';
  const HOSTED_AGENT_URL = 'https://agent-production-8568.up.railway.app';
  const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || process.env.ARCEUS_AGENT_URL || (process.env.NODE_ENV === 'production' ? HOSTED_AGENT_URL : 'http://localhost:8003');

  if (
    path.startsWith('/api/v1/auth') ||
    path.startsWith('/api/v1/integrations') ||
    path.startsWith('/api/v1/me')
  ) {
    return AUTH_URL + path;
  }
  if (
    path.startsWith('/api/v1/goals') ||
    path.startsWith('/api/v1/tasks') ||
    path.startsWith('/api/v1/schedules') ||
    path.startsWith('/api/v1/analytics') ||
    path.startsWith('/api/v1/approvals')
  ) {
    return GOALS_URL + path;
  }
  if (
    path.startsWith('/api/v1/agents') ||
    path.startsWith('/api/v1/models') ||
    path.startsWith('/api/v1/files') ||
    path.startsWith('/api/v1/github') ||
    path.startsWith('/api/v1/competitive-position') ||
    path.startsWith('/api/v1/usage') ||
    path.startsWith('/api/v1/billing') ||
    path.startsWith('/api/v1/admin') ||
    path.startsWith('/api/v1/plugins') ||
    path.startsWith('/api/v1/pa') ||
    path.startsWith('/api/v1/code') ||
    path.startsWith('/api/v1/internet') ||
    path.startsWith('/api/v1/free-tiers') ||
    path.startsWith('/api/v1/design') ||
    path.startsWith('/api/v1/deploy') ||
    path.startsWith('/api/v1/downloads') ||
    path.startsWith('/api/v1/repositories') ||
    path.startsWith('/api/v1/missions') ||
    path.startsWith('/api/v1/intelligence') ||
    path.startsWith('/api/v1/safety') ||
    path.startsWith('/api/v1/memories') ||
    path.startsWith('/api/v1/news') ||
    path.startsWith('/api/v1/jobs') ||
    path.startsWith('/api/v1/os') ||
    path.startsWith('/api/v1/runtime') ||
    path.startsWith('/api/v1/task-runtime') ||
    path.startsWith('/api/v1/platform') ||
    path.startsWith('/api/v1/learning') ||
    path.startsWith('/api/v1/strategy') ||
    path.startsWith('/api/v1/kernel') ||
    path.startsWith('/api/v1/compute') ||
    path.startsWith('/api/v1/graph') ||
    path.startsWith('/api/v1/governance') ||
    path.startsWith('/api/v1/memory') ||
    path.startsWith('/api/v1/research') ||
    path.startsWith('/api/v1/extensions') ||
    path.startsWith('/api/v1/verification-engine') ||
    path.startsWith('/api/v1/federation') ||
    path.startsWith('/api/v1/civilization') ||
    path.startsWith('/api/v1/product') ||
    path.startsWith('/api/v1/automation') ||
    path.startsWith('/api/v1/intents') ||
    path.startsWith('/api/v1/workspace') ||
    path.startsWith('/api/v1/timeline') ||
    path.startsWith('/api/v1/dashboard') ||
    path.startsWith('/api/v1/voice') ||
    path.startsWith('/api/v1/search') ||
    path.startsWith('/api/v1/sessions')
  ) {
    return AGENT_URL + path;
  }
  return GOALS_URL + path; // Fallback
}

const DEMO_USER_ID = process.env.NEXT_PUBLIC_DEMO_USER_ID || '00000000-0000-0000-0000-000000000000';
const REQUIRE_AUTH = process.env.NEXT_PUBLIC_REQUIRE_AUTH === 'true';
const PUBLIC_APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV || '').toLowerCase();
const PRODUCTION_LIKE_FRONTEND = PUBLIC_APP_ENV === 'production' || PUBLIC_APP_ENV === 'staging';
const ALLOW_DEMO_HEADER = !REQUIRE_AUTH && !PRODUCTION_LIKE_FRONTEND;

export class ApiError extends Error {
  status: number;
  detail: any;
  payload: any;

  constructor(message: string, status: number, detail: any, payload: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }
}

export function createApiHeaders(options: RequestInit = {}): Headers {
  const headers = new Headers(options.headers || {});

  if (typeof window !== 'undefined') {
    const authState = readDesktopAuthState();
    const storedToken = authState.accessToken;
    const storedUserId = authState.userId || (ALLOW_DEMO_HEADER ? DEMO_USER_ID : '');

    if (storedToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${storedToken}`);
    }
    if (storedUserId && !headers.has('x-user-id')) {
      headers.set('x-user-id', storedUserId);
    }
    const storedVaultKey = window.sessionStorage.getItem('my-ai.vault_key');
    if (storedVaultKey && !headers.has('x-vault-key')) {
      headers.set('x-vault-key', storedVaultKey);
    }
  } else if (ALLOW_DEMO_HEADER && !headers.has('x-user-id')) {
    headers.set('x-user-id', DEMO_USER_ID);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  return headers;
}

async function getClerkToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  const clerk = (window as any).Clerk;
  try {
    if (clerk?.session?.getToken) {
      return await clerk.session.getToken();
    }
  } catch {
    return null;
  }
  return null;
}

export async function createApiHeadersAsync(options: RequestInit = {}): Promise<Headers> {
  const headers = createApiHeaders(options);
  const clerkToken = await getClerkToken();
  if (clerkToken) {
    headers.set('Authorization', `Bearer ${clerkToken}`);
    headers.delete('x-user-id');
  }
  return headers;
}

export async function apiRequest(path: string, options: RequestInit = {}): Promise<any> {
  const url = getServiceUrl(path);
  const headers = await createApiHeadersAsync(options);
  const isLocalDesktopService = typeof window !== 'undefined'
    && /^http:\/\/127\.0\.0\.1:800[23]\//.test(url)
    && !path.startsWith('/api/v1/auth');
  if (isLocalDesktopService) {
    headers.delete('Authorization');
  }

  const response = await fetch(url, { ...options, headers });
  
  if (!response.ok) {
    let err;
    try {
      err = await response.json();
    } catch {
      err = { detail: response.statusText };
    }
    const detail = err?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || err?.message || err?.error || 'API request failed';
    if (!isLocalDesktopService && typeof window !== 'undefined' && (response.status === 401 || response.status === 403) && readDesktopAuthState().connected) {
      clearDesktopAuthState();
    }
    throw new ApiError(message, response.status, detail, err);
  }
  
  // Return empty object on 204 or empty response
  if (response.status === 204) {
    return {};
  }
  
  return response.json();
}
