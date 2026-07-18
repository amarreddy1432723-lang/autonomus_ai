import { NextRequest } from 'next/server';

const HOSTED_AGENT_URL = 'https://agent-production-8568.up.railway.app';
const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL || process.env.ARCEUS_AGENT_URL || (process.env.NODE_ENV === 'production' ? HOSTED_AGENT_URL : 'http://localhost:8003');

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = `${agentUrl}/api/v1/downloads/${path.join('/')}${request.nextUrl.search}`;

  const response = await fetch(target, {
    method: request.method,
    headers: {
      accept: request.headers.get('accept') || 'application/json',
    },
    cache: 'no-store',
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      'cache-control': 'no-store',
      'content-type': response.headers.get('content-type') || 'application/json',
    },
  });
}

export const GET = proxy;
