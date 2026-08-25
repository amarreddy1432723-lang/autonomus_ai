import type { ArceusClientSurface, ArceusRouteBoundary } from '@/types/arceus-frontend';

type RouteBoundary = {
  prefix: string;
  boundary: ArceusRouteBoundary;
  surfaces: ArceusClientSurface[];
  requiresAuth: boolean;
  desktopAllowed: boolean;
};

export const desktopCodeAlphaPrefixes = [
  '/launch',
  '/onboarding',
  '/workspace',
  '/mission-control',
  '/settings',
  '/auth/desktop',
  '/download',
] as const;

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
  { prefix: '/onboarding', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/idea-discovery', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/product-intelligence', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/domain-intelligence', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/product-blueprint', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/architecture-strategy', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/technology-stack', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/engineering-roadmap', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/ai-workforce', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/executive-review', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/mission-control', boundary: 'workspace', surfaces: ['desktop', 'web'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/evolution-center', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/knowledge-graph', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/organization-network', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/intelligence-kernel', boundary: 'workspace', surfaces: ['web'], requiresAuth: false, desktopAllowed: false },
  { prefix: '/settings', boundary: 'settings', surfaces: ['web', 'desktop'], requiresAuth: false, desktopAllowed: true },
  { prefix: '/ui-preview', boundary: 'workspace', surfaces: ['desktop'], requiresAuth: false, desktopAllowed: false },
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
  if (pathname === '/ui-preview' || pathname.startsWith('/ui-preview/')) {
    return process.env.NEXT_PUBLIC_ENABLE_UI_PREVIEWS === 'true';
  }
  return desktopCodeAlphaPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
