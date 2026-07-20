import type { ArceusClientSurface, ArceusRouteBoundary } from '@/types/arceus-frontend';

type RouteBoundary = {
  prefix: string;
  boundary: ArceusRouteBoundary;
  surfaces: ArceusClientSurface[];
  requiresAuth: boolean;
  desktopAllowed: boolean;
};

export const routeBoundaries: RouteBoundary[] = [
  { prefix: '/admin', boundary: 'admin', surfaces: ['admin'], requiresAuth: true, desktopAllowed: false },
  { prefix: '/sign-in', boundary: 'auth', surfaces: ['auth', 'web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/sign-up', boundary: 'auth', surfaces: ['auth', 'web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/login', boundary: 'auth', surfaces: ['auth', 'web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/signup', boundary: 'auth', surfaces: ['auth', 'web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/auth/desktop', boundary: 'auth', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/docs', boundary: 'docs', surfaces: ['docs', 'web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/download', boundary: 'marketing', surfaces: ['web', 'desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/pricing', boundary: 'marketing', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/products', boundary: 'marketing', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/workspace', boundary: 'workspace', surfaces: ['web', 'desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/launch', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/idea-discovery', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/product-intelligence', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/domain-intelligence', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/product-blueprint', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/architecture-strategy', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/technology-stack', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/engineering-roadmap', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/ai-workforce', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/executive-review', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/mission-control', boundary: 'workspace', surfaces: ['desktop', 'web'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/evolution-center', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/knowledge-graph', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/organization-network', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/intelligence-kernel', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/settings', boundary: 'settings', surfaces: ['web', 'desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/ui-preview', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
];

export function getRouteBoundary(pathname: string): RouteBoundary {
  return (
    routeBoundaries
      .filter((route) => pathname === route.prefix || pathname.startsWith(`${route.prefix}/`))
      .sort((a, b) => b.prefix.length - a.prefix.length)[0] || {
      prefix: pathname,
      boundary: 'unknown',
      surfaces: ['web'],
      requiresAuth: false,
      desktopAllowed: false,
    }
  );
}

export function isDesktopRouteAllowed(pathname: string) {
  return getRouteBoundary(pathname).desktopAllowed;
}
