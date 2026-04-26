"use client";

import { type ReactNode } from "react";
import { usePathname } from "next/navigation";
import {
  AppShell,
  Header,
  ResponsiveSidebar,
  type SidebarItem,
} from "@bsvibe/layout";
import { useAuth } from "../hooks/useAuth";
import { MaterialIcon } from "../components/MaterialIcon";

/**
 * BSupervisor application chrome — Phase A consumer of `@bsvibe/layout`.
 *
 * `AppShell` provides the RSC-eligible sidebar+header+main grid; the
 * inner sidebar / header content remains BSupervisor-specific. The
 * `bsvibe-sidebar*` class hooks are styled in `app/globals.css` so the
 * existing visual language (gray-950 chrome, accent rose pills) survives
 * unchanged.
 */

const NAV_ITEMS: SidebarItem[] = [
  {
    href: "/",
    label: "Dashboard",
    icon: <MaterialIcon icon="dashboard" className="text-xl" />,
  },
  {
    href: "/incidents",
    label: "Incidents",
    icon: <MaterialIcon icon="timeline" className="text-xl" />,
  },
  {
    href: "/rules",
    label: "Rules",
    icon: <MaterialIcon icon="gavel" className="text-xl" />,
  },
  {
    href: "/reports",
    label: "Reports",
    icon: <MaterialIcon icon="analytics" className="text-xl" />,
  },
  {
    href: "/costs",
    label: "Costs",
    icon: <MaterialIcon icon="payments" className="text-xl" />,
  },
  {
    href: "/settings",
    label: "Settings",
    icon: <MaterialIcon icon="settings" className="text-xl" />,
  },
];

const PAGE_TITLES: Record<string, string> = {
  "/": "Safety Dashboard",
  "/incidents": "Incident Timeline",
  "/rules": "Rules Manager",
  "/reports": "Daily Report",
  "/costs": "Cost Monitor",
  "/settings": "Settings",
};

function Logo() {
  return (
    <div className="flex items-center gap-3 px-6 py-8">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-900">
        <MaterialIcon icon="security" className="text-2xl text-accent" filled />
      </div>
      <div>
        <span className="text-xl font-black text-accent tracking-tighter">
          BSupervisor
        </span>
        <span className="block text-[10px] font-bold tracking-[0.2em] text-gray-500 uppercase">
          AI Sentinel
        </span>
      </div>
    </div>
  );
}

function UserCard() {
  const { user, logout } = useAuth();
  return (
    <div className="border-t border-gray-800/10 px-4 py-4">
      {user && (
        <div className="mb-2 flex items-center gap-3 rounded-xl bg-gray-900 p-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-xs font-bold text-accent">
            {user.email.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1 overflow-hidden">
            <p className="truncate text-xs font-bold text-gray-200">
              {user.email}
            </p>
            <p className="truncate text-[10px] text-gray-500">{user.role}</p>
          </div>
        </div>
      )}
      <button
        onClick={logout}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-gray-500 transition-colors hover:bg-gray-900 hover:text-gray-300"
      >
        <MaterialIcon icon="logout" className="text-lg" />
        Sign out
      </button>
    </div>
  );
}

function HeaderRightSlot() {
  return (
    <div className="flex items-center gap-6">
      <div className="relative items-center hidden sm:flex">
        <MaterialIcon
          icon="search"
          className="absolute left-3 text-sm text-gray-500"
        />
        <input
          type="text"
          placeholder="Search events..."
          className="rounded-full bg-gray-900 border-none py-1.5 pl-10 pr-4 text-xs w-64 text-gray-100 placeholder-gray-500 outline-none focus:ring-1 focus:ring-accent/50"
        />
      </div>
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
          Live Surveillance
        </span>
      </div>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const title = PAGE_TITLES[pathname] ?? "BSupervisor";

  return (
    <AppShell
      sidebar={
        <ResponsiveSidebar
          items={NAV_ITEMS}
          logo={<Logo />}
          footer={<UserCard />}
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
