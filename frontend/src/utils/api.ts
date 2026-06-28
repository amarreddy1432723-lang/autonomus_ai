
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
  if (path.startsWith('/api/v1/agents')) {
    return AGENT_URL + path;
  }
  return GOALS_URL + path; // Fallback
}

export async function apiRequest(path: string, options: RequestInit = {}): Promise<any> {
  const url = getServiceUrl(path);
  const headers = new Headers(options.headers || {});
  
  // Attach default test user UUID and credentials
  headers.set('x-user-id', '00000000-0000-0000-0000-000000000000');
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

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
