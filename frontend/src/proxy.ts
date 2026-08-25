import { NextResponse, type NextRequest } from 'next/server';

const publicRoutePrefixes = [
  '/',
  '/hub',
  '/download',
  '/auth/desktop',
  '/login',
  '/signup',
  '/sign-in',
  '/sign-up',
  '/api/public',
  '/api/v1',
];
const desktopLocalRoutePrefixes = [
  '/launch',
  '/workspace',
  '/onboarding',
  '/settings',
  '/mission-control',
];

const requireAuth = process.env.NEXT_PUBLIC_REQUIRE_AUTH === 'true';
const publicAppEnv = (process.env.NEXT_PUBLIC_APP_ENV || '').toLowerCase();
const productionLikeFrontend = publicAppEnv === 'production' || publicAppEnv === 'staging';
const effectiveRequireAuth = requireAuth || productionLikeFrontend;

function isElectronRequest(request: NextRequest): boolean {
  const userAgent = request.headers.get('user-agent') || '';
  return /Electron|Arceus Code/i.test(userAgent);
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  if (prefix === '/') return pathname === '/';
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function isAllowedWithoutWebSession(request: NextRequest): boolean {
  const pathname = request.nextUrl.pathname;
  return publicRoutePrefixes.some((prefix) => matchesPrefix(pathname, prefix))
    || (isElectronRequest(request) && desktopLocalRoutePrefixes.some((prefix) => matchesPrefix(pathname, prefix)));
}

export default function proxy(request: NextRequest) {
  if (!effectiveRequireAuth) {
    return NextResponse.next();
  }

  const isProtected = !isAllowedWithoutWebSession(request);
  const mockToken = request.cookies.get('my-ai.mock_token')?.value;
  const isApiRoute = request.nextUrl.pathname.startsWith('/api/');
  const hasDemoUserHeader = !!request.headers.get('x-user-id');

  if (isProtected && !mockToken && !(isApiRoute && hasDemoUserHeader)) {
    const signInUrl = new URL('/sign-in', request.url);
    signInUrl.searchParams.set('redirect_url', request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(signInUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
};
