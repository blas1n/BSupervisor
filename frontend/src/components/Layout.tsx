import { useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";
import { cn } from "../lib/utils";
import { useAuth } from "../lib/auth";
import { MaterialIcon } from "../components/MaterialIcon";

const navItems = [
  { to: "/", icon: "dashboard", label: "Dashboard" },
  { to: "/rules", icon: "gavel", label: "Rules" },
  { to: "/reports", icon: "analytics", label: "Reports" },
  { to: "/costs", icon: "payments", label: "Costs" },
  { to: "/settings", icon: "settings", label: "Settings" },
];

const pageTitles: Record<string, string> = {
  "/": "Safety Dashboard",
  "/rules": "Rules Manager",
  "/reports": "Daily Report",
  "/costs": "Cost Monitor",
  "/settings": "Settings",
};


export function Layout() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const title = pageTitles[location.pathname] ?? "BSupervisor";
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Backdrop - mobile only */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`fixed left-0 top-0 h-screen w-64 flex-shrink-0 flex flex-col bg-gray-950 z-50 transform transition-transform duration-200 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0 md:static md:z-auto`}>
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 py-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-900">
            <MaterialIcon icon="security" className="text-2xl text-accent" filled />
          </div>
          <div>
            <span className="text-xl font-black text-accent tracking-tighter">BSupervisor</span>
            <span className="block text-[10px] font-bold tracking-[0.2em] text-gray-500 uppercase">
              AI Sentinel
            </span>
          </div>
        </div>

        {/* Nav */}
        <nav className="mt-4 flex flex-1 flex-col gap-1 px-3">
          {navItems.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-3 text-sm uppercase font-bold tracking-tight transition-all duration-200",
                  isActive
                    ? "text-gray-50 bg-gray-900 rounded-lg border-l-4 border-accent"
                    : "text-gray-500 hover:text-gray-200 hover:bg-gray-900",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <MaterialIcon
                    icon={icon}
                    className="text-xl"
                    filled={isActive}
                  />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User & Logout */}
        <div className="border-t border-gray-800/10 px-4 py-4 mt-auto">
          {user && (
            <div className="mb-2 flex items-center gap-3 rounded-xl bg-gray-900 p-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-xs font-bold text-accent">
                {(user.name || "U").charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1 overflow-hidden">
                <p className="truncate text-xs font-bold text-gray-200">
                  {user.name || "User"}
                </p>
                <p className="truncate text-[10px] text-gray-500">
                  {user.email}
                </p>
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
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden bg-gray-950">
        {/* Header */}
        <header className="flex h-16 flex-shrink-0 items-center justify-between bg-gray-950/60 px-8 backdrop-blur-xl sticky top-0 z-40">
          <div className="flex items-center gap-4">
            {/* Hamburger - mobile only */}
            <button
              className="md:hidden p-2 -ml-2 rounded-lg text-gray-400"
              onClick={() => setSidebarOpen(true)}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <h2 className="text-sm text-gray-400 font-medium">
              {title}
            </h2>
            <div className="h-4 w-px bg-gray-700/30" />
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
              </span>
              <span className="text-[10px] uppercase tracking-widest text-accent font-bold">Live Surveillance</span>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="relative flex items-center hidden sm:flex">
              <MaterialIcon icon="search" className="absolute left-3 text-sm text-gray-500" />
              <input
                type="text"
                placeholder="Search events..."
                className="rounded-full bg-gray-900 border-none py-1.5 pl-10 pr-4 text-xs w-64 text-gray-100 placeholder-gray-500 outline-none focus:ring-1 focus:ring-accent/50"
              />
            </div>
            <div className="flex items-center gap-4 text-gray-400">
              <MaterialIcon icon="notifications" className="hover:text-accent cursor-pointer transition-colors duration-300" />
              <MaterialIcon icon="settings" className="hover:text-accent cursor-pointer transition-colors duration-300" />
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
