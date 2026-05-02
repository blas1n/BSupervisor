/**
 * next-intl request config — composes shared `@bsvibe/i18n` namespaces
 * (`common`, `auth`) with the BSupervisor-local `supervisor` namespace.
 *
 * BSupervisor pins `defaultLocale: 'en'` because the existing UI and
 * Playwright e2e suite assert on English copy. Korean is opt-in via the
 * `/ko` URL prefix produced by the `localePrefix: 'as-needed'` middleware.
 */
import { getRequestConfig as defineRequestConfig } from 'next-intl/server';
import {
  getRequestConfig as buildSharedConfig,
  resolveLocale,
} from '@bsvibe/i18n';

const SUPERVISOR_DEFAULT_LOCALE = 'en' as const;

export default defineRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = resolveLocale(requested, SUPERVISOR_DEFAULT_LOCALE);

  const supervisorMessages = (
    await import(`../messages/supervisor.${locale}.json`)
  ).default;

  const shared = await buildSharedConfig({
    locale,
    extra: { supervisor: supervisorMessages },
  });

  return {
    locale,
    messages: shared.messages,
  };
});
