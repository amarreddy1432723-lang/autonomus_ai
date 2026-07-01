import { NextResponse, type NextRequest } from 'next/server';

export default function proxy(_request: NextRequest) {
  // Backend services enforce auth. Keep the frontend bootable until Clerk env keys
  // are configured in Railway/Vercel.
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
