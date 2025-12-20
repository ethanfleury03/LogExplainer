import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const devBypass = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === 'true';
  const isProduction = process.env.NODE_ENV === 'production';
  const pathname = request.nextUrl.pathname;

  // In production without bypass, block access until real auth is wired
  if (isProduction && !devBypass) {
    // TODO: Validate portal JWT/cookie here
    // For now, allow all routes (will be implemented when portal auth is integrated)
    return NextResponse.next();
  }

  // Admin-only routes
  if (pathname.startsWith('/index-manager')) {
    // In dev bypass mode, allow access (role check happens in component)
    // In production, would check JWT/cookie for admin role here
    if (!devBypass && isProduction) {
      // TODO: Check admin role from session
      // For now, allow (will be implemented with portal auth)
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
};

