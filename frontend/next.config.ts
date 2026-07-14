import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(self), geolocation=()',
          },
        ],
      },
    ];
  },
  async rewrites() {
    const authUrl = process.env.NEXT_PUBLIC_AUTH_URL || 'http://localhost:8001';
    const goalsUrl = process.env.NEXT_PUBLIC_GOALS_URL || 'http://localhost:8002';
    const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8003';

    return [
      {
        source: '/api/v1/auth/:path*',
        destination: `${authUrl}/api/v1/auth/:path*`,
      },
      {
        source: '/api/v1/integrations/:path*',
        destination: `${authUrl}/api/v1/integrations/:path*`,
      },
      {
        source: '/api/v1/me',
        destination: `${authUrl}/api/v1/me`,
      },
      {
        source: '/api/v1/goals/:path*',
        destination: `${goalsUrl}/api/v1/goals/:path*`,
      },
      {
        source: '/api/v1/tasks/:path*',
        destination: `${goalsUrl}/api/v1/tasks/:path*`,
      },
      {
        source: '/api/v1/schedules/:path*',
        destination: `${goalsUrl}/api/v1/schedules/:path*`,
      },
      {
        source: '/api/v1/analytics/:path*',
        destination: `${goalsUrl}/api/v1/analytics/:path*`,
      },
      {
        source: '/api/v1/approvals/:path*',
        destination: `${goalsUrl}/api/v1/approvals/:path*`,
      },
      {
        source: '/api/v1/agents/:path*',
        destination: `${agentUrl}/api/v1/agents/:path*`,
      },
      {
        source: '/api/v1/models/:path*',
        destination: `${agentUrl}/api/v1/models/:path*`,
      },
      {
        source: '/api/v1/interview/:path*',
        destination: `${agentUrl}/api/v1/interview/:path*`,
      },
      {
        source: '/api/v1/memories/:path*',
        destination: `${agentUrl}/api/v1/memories/:path*`,
      },
      {
        source: '/api/v1/news/:path*',
        destination: `${agentUrl}/api/v1/news/:path*`,
      },
      {
        source: '/api/v1/jobs/:path*',
        destination: `${agentUrl}/api/v1/jobs/:path*`,
      },
      {
        source: '/api/v1/sessions/:path*',
        destination: `${agentUrl}/api/v1/sessions/:path*`,
      },
      {
        source: '/api/v1/files/:path*',
        destination: `${agentUrl}/api/v1/files/:path*`,
      },
      {
        source: '/api/v1/usage/:path*',
        destination: `${agentUrl}/api/v1/usage/:path*`,
      },
      {
        source: '/api/v1/billing/:path*',
        destination: `${agentUrl}/api/v1/billing/:path*`,
      },
      {
        source: '/api/v1/pa/:path*',
        destination: `${agentUrl}/api/v1/pa/:path*`,
      },
      {
        source: '/api/v1/code/:path*',
        destination: `${agentUrl}/api/v1/code/:path*`,
      },
      {
        source: '/api/v1/internet/:path*',
        destination: `${agentUrl}/api/v1/internet/:path*`,
      },
      {
        source: '/api/v1/free-tiers/:path*',
        destination: `${agentUrl}/api/v1/free-tiers/:path*`,
      },
      {
        source: '/api/v1/design/:path*',
        destination: `${agentUrl}/api/v1/design/:path*`,
      },
      {
        source: '/api/v1/deploy/:path*',
        destination: `${agentUrl}/api/v1/deploy/:path*`,
      },
      {
        source: '/api/v1/downloads/:path*',
        destination: `${agentUrl}/api/v1/downloads/:path*`,
      },
      {
        source: '/api/v1/intelligence/:path*',
        destination: `${agentUrl}/api/v1/intelligence/:path*`,
      },
      {
        source: '/api/v1/safety/:path*',
        destination: `${agentUrl}/api/v1/safety/:path*`,
      },
    ];
  },
};

export default nextConfig;
