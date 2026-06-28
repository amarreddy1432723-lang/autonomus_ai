import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/v1/auth/:path*',
        destination: 'http://localhost:8001/api/v1/auth/:path*',
      },
      {
        source: '/api/v1/integrations/:path*',
        destination: 'http://localhost:8001/api/v1/integrations/:path*',
      },
      {
        source: '/api/v1/me',
        destination: 'http://localhost:8001/api/v1/me',
      },
      {
        source: '/api/v1/goals/:path*',
        destination: 'http://localhost:8002/api/v1/goals/:path*',
      },
      {
        source: '/api/v1/tasks/:path*',
        destination: 'http://localhost:8002/api/v1/tasks/:path*',
      },
      {
        source: '/api/v1/schedules/:path*',
        destination: 'http://localhost:8002/api/v1/schedules/:path*',
      },
      {
        source: '/api/v1/analytics/:path*',
        destination: 'http://localhost:8002/api/v1/analytics/:path*',
      },
      {
        source: '/api/v1/approvals/:path*',
        destination: 'http://localhost:8002/api/v1/approvals/:path*',
      },
      {
        source: '/api/v1/agents/:path*',
        destination: 'http://localhost:8003/api/v1/agents/:path*',
      },
    ];
  },
};

export default nextConfig;
