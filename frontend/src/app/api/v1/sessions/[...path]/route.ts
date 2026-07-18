import { NextRequest } from 'next/server';

const HOSTED_AGENT_URL = 'https://agent-production-8568.up.railway.app';
const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL || process.env.ARCEUS_AGENT_URL || (process.env.NODE_ENV === 'production' ? HOSTED_AGENT_URL : 'http://localhost:8003');

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = `${agentUrl}/api/v1/sessions/${path.join('/')}${request.nextUrl.search}`;
  const body = request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.text();

  const response = await fetch(target, {
    method: request.method,
    headers: {
      'content-type': request.headers.get('content-type') || 'application/json',
      'authorization': request.headers.get('authorization') || '',
      'x-user-id': request.headers.get('x-user-id') || '',
    },
    body,
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      'content-type': response.headers.get('content-type') || 'application/json',
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
