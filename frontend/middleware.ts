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

export default createI18nMiddleware({
  locales: ['ko', 'en'],
  defaultLocale: 'en',
  localePrefix: 'as-needed',
});

// NOTE: Next.js parses `config.matcher` statically — spread operators or
// computed values are rejected (`Invalid page config`). The literal mirrors
// `defaultMatcher` from `@bsvibe/i18n/middleware`; keep them in sync.
export const config = {
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
};
