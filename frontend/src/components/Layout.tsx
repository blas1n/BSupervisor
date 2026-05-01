"use client";

import { type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useT, useCurrentLocale } from "@bsvibe/i18n";
import {
  AppShell,
  Header,
  ResponsiveSidebar,
  SidebarBrand,
  SidebarUserCard,
  type SidebarItem,
} from "@bsvibe/layout";
import { useAuth } from "../hooks/useAuth";
import { MaterialIcon } from "../components/MaterialIcon";

/**
 * BSupervisor application chrome — Phase A consumer of `@bsvibe/layout`.
 *
 * Phase C i18n: nav labels, page titles, header search placeholder,
 * "Sign out" button, brand tagline, and live-status badge are loaded from
 * the `supervisor` next-intl namespace via `useT()`. A header-mounted
 * locale switcher toggles between `en` (default, no URL prefix) and `ko`
 * (`/ko/...`).
 */

const NAV_KEYS = [
  { href: "/", labelKey: "dashboard", icon: "dashboard" },
  { href: "/incidents", labelKey: "incidents", icon: "timeline" },
  { href: "/rules", labelKey: "rules", icon: "gavel" },
  { href: "/reports", labelKey: "reports", icon: "analytics" },
  { href: "/costs", labelKey: "costs", icon: "payments" },
  { href: "/settings", labelKey: "settings", icon: "settings" },
] as const;

const PAGE_TITLE_KEYS: Record<string, string> = {
  "/": "dashboard",
  "/incidents": "incidents",
  "/rules": "rules",
  "/reports": "reports",
  "/costs": "costs",
  "/settings": "settings",
};

function LocaleSwitcher() {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const current = useCurrentLocale();

  function switchTo(next: "ko" | "en") {
    if (next === current) return;
    // Strip any leading `/ko` or `/en` segment, then re-prefix only when
    // switching to the non-default locale (`ko`). Default `en` is bare-rooted
    // because middleware uses `localePrefix: 'as-needed'` with default `en`.
    const stripped = pathname.replace(/^\/(ko|en)(?=\/|$)/, "") || "/";
    const nextPath = next === "ko" ? `/ko${stripped === "/" ? "" : stripped}` : stripped;
    router.replace(nextPath);
  }

  return (
    <div className="flex items-center gap-1 rounded-full bg-gray-900 p-1 text-[10px] font-bold uppercase tracking-widest">
      <button
        type="button"
        onClick={() => switchTo("en")}
        aria-pressed={current === "en"}
        data-testid="locale-en"
        className={`min-h-10 min-w-10 rounded-full px-2 py-1 transition-colors ${
          current === "en" ? "bg-accent/15 text-accent" : "text-gray-400 hover:text-gray-200"
        }`}
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => switchTo("ko")}
        aria-pressed={current === "ko"}
        data-testid="locale-ko"
        className={`min-h-10 min-w-10 rounded-full px-2 py-1 transition-colors ${
          current === "ko" ? "bg-accent/15 text-accent" : "text-gray-400 hover:text-gray-200"
        }`}
      >
        KO
      </button>
    </div>
  );
}

function HeaderRightSlot() {
  const t = useT("supervisor.header");
  return (
    <div className="flex items-center gap-6">
      <div className="relative items-center hidden sm:flex">
        <MaterialIcon
          icon="search"
          className="absolute left-3 text-sm text-gray-500"
        />
        <input
          type="text"
          placeholder={t("searchPlaceholder")}
          className="rounded-full bg-gray-900 border-none py-1.5 pl-10 pr-4 text-xs w-64 text-gray-100 placeholder-gray-500 outline-none focus:ring-1 focus:ring-accent/50"
        />
      </div>
      <LocaleSwitcher />
      <div className="flex items-center gap-4 text-gray-400">
        <MaterialIcon
          icon="notifications"
          className="hover:text-accent cursor-pointer transition-colors duration-300"
        />
        <MaterialIcon
          icon="settings"
          className="hover:text-accent cursor-pointer transition-colors duration-300"
        />
      </div>
    </div>
  );
}

function HeaderTitle({ title }: { title: string }) {
  const t = useT("supervisor.branding");
  return (
    <div className="flex items-center gap-4">
      <h2 className="text-sm text-gray-400 font-medium">{title}</h2>
      <div className="h-4 w-px bg-gray-700/30" />
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
        </span>
        <span className="text-[10px] uppercase tracking-widest text-accent font-bold">
          {t("liveStatus")}
        </span>
      </div>
    </div>
  );
}

function normalizePath(pathname: string): string {
  // Strip locale prefix so route → title lookup ignores `/ko` etc.
  const stripped = pathname.replace(/^\/(ko|en)(?=\/|$)/, "");
  return stripped === "" ? "/" : stripped;
}

export function Layout({ children }: { children: ReactNode }) {
  const tNav = useT("supervisor.nav");
  const tTitles = useT("supervisor.pageTitles");
  const tBranding = useT("supervisor.branding");
  const tUserMenu = useT("supervisor.userMenu");
  const { user, logout } = useAuth();
  const pathname = usePathname() ?? "/";
  const normalized = normalizePath(pathname);
  const titleKey = PAGE_TITLE_KEYS[normalized] ?? null;
  const title = titleKey ? tTitles(titleKey) : "BSupervisor";

  const navItems: SidebarItem[] = NAV_KEYS.map((item) => ({
    href: item.href,
    label: tNav(item.labelKey),
    icon: <MaterialIcon icon={item.icon} className="text-xl" />,
  }));

  return (
    <AppShell
      sidebar={
        <ResponsiveSidebar
          items={navItems}
          logo={
            <SidebarBrand
              icon={<MaterialIcon icon="security" filled />}
              name="BSupervisor"
              tagline={tBranding("tagline")}
            />
          }
          footer={
            user ? (
              <SidebarUserCard
                email={user.email}
                role={user.role}
                onSignOut={logout}
                signOutLabel={tUserMenu("signOut")}
              />
            ) : null
          }
          ariaLabel="BSupervisor primary navigation"
        />
      }
      header={
        <Header title={<HeaderTitle title={title} />} rightSlot={<HeaderRightSlot />} />
      }
    >
      {children}
    </AppShell>
  );
}
