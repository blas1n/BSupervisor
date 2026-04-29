/**
 * BSupervisor i18n middleware — Phase C.
 *
 * Uses the BSVibe shared `@bsvibe/i18n/middleware` factory so the locale
 * routing stays consistent across all consumer products. BSupervisor
 * deliberately pins `defaultLocale: 'en'` (overriding the package default of
 * `ko`) because the existing UI copy and Playwright e2e suite assert on
 * English. Korean is opt-in via `/ko/...` URL prefix.
 */
import { createI18nMiddleware } from '@bsvibe/i18n/middleware';
import { NextResponse, type NextRequest } from 'next/server';

const i18nMiddleware = createI18nMiddleware({
  locales: ['ko', 'en'],
  defaultLocale: 'en',
  localePrefix: 'as-needed',
});

const PUBLIC_PATHS = new Set(['/login', '/en/login', '/ko/login']);

export default function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSessionCookie = request.cookies.has('bsvibe_session');

  if (!hasSessionCookie && !PUBLIC_PATHS.has(pathname)) {
    const localePrefix = pathname.startsWith('/ko') ? '/ko' : pathname.startsWith('/en') ? '/en' : '';
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = `${localePrefix}/login`;
    loginUrl.search = '';
    return NextResponse.redirect(loginUrl);
  }

  return i18nMiddleware(request);
}

// NOTE: Next.js parses `config.matcher` statically — spread operators or
// computed values are rejected (`Invalid page config`). The literal mirrors
// `defaultMatcher` from `@bsvibe/i18n/middleware`; keep them in sync.
export const config = {
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
};
