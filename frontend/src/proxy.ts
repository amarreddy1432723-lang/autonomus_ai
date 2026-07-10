import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse, type NextRequest } from 'next/server';

const isPublicRoute = createRouteMatcher([
  '/',
  '/hub(.*)',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api/public(.*)',
  '/api/v1(.*)'
]);

const hasClerkKeys = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const requireAuth = process.env.NEXT_PUBLIC_REQUIRE_AUTH === 'true';

export default function proxy(request: NextRequest, event: any) {
  if (hasClerkKeys) {
    return clerkMiddleware(async (auth, req) => {
      if (!isPublicRoute(req)) {
        await auth.protect();
      }
    })(request, event);
  }

  // Mock authentication fallback for demo mode
  if (!requireAuth) {
    return NextResponse.next();
  }

  const isProtected = !isPublicRoute(request);
  const mockToken = request.cookies.get('my-ai.mock_token')?.value;
  const isApiRoute = request.nextUrl.pathname.startsWith('/api/');
  const hasDemoUserHeader = !!request.headers.get('x-user-id');

  if (isProtected && !mockToken && !(isApiRoute && hasDemoUserHeader)) {
    const signInUrl = new URL('/sign-in', request.url);
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
