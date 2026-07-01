
export function getServiceUrl(path: string): string {
  if (typeof window !== 'undefined') {
    return path;
  }
  
  const AUTH_URL = process.env.NEXT_PUBLIC_AUTH_URL || 'http://localhost:8001';
  const GOALS_URL = process.env.NEXT_PUBLIC_GOALS_URL || 'http://localhost:8002';
  const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8003';

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
    path.startsWith('/api/v1/files') ||
    path.startsWith('/api/v1/usage') ||
    path.startsWith('/api/v1/code') ||
    path.startsWith('/api/v1/memories') ||
    path.startsWith('/api/v1/news') ||
    path.startsWith('/api/v1/jobs') ||
    path.startsWith('/api/v1/sessions')
  ) {
    return AGENT_URL + path;
  }
  return GOALS_URL + path; // Fallback
}

const DEMO_USER_ID = process.env.NEXT_PUBLIC_DEMO_USER_ID || '00000000-0000-0000-0000-000000000000';
const REQUIRE_AUTH = process.env.NEXT_PUBLIC_REQUIRE_AUTH === 'true';

export function createApiHeaders(options: RequestInit = {}): Headers {
  const headers = new Headers(options.headers || {});

  if (typeof window !== 'undefined') {
    const storedToken = window.localStorage.getItem('my-ai.access_token');
    const storedUserId = window.localStorage.getItem('my-ai.user_id') || (REQUIRE_AUTH ? '' : DEMO_USER_ID);

    if (storedToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${storedToken}`);
    }
    if (storedUserId && !headers.has('x-user-id')) {
      headers.set('x-user-id', storedUserId);
    }
  } else if (!REQUIRE_AUTH && !headers.has('x-user-id')) {
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

  const response = await fetch(url, { ...options, headers });
  
  if (!response.ok) {
    let err;
    try {
      err = await response.json();
    } catch {
      err = { detail: response.statusText };
    }
    throw new Error(err.detail || 'API request failed');
  }
  
  // Return empty object on 204 or empty response
  if (response.status === 204) {
    return {};
  }
  
  return response.json();
}
