import { Outlet, NavLink, useLocation } from "react-router-dom";
import { cn } from "../lib/utils";
import { useAuth } from "../lib/auth";
import { MaterialIcon } from "../components/MaterialIcon";

const navItems = [
  { to: "/", icon: "dashboard", label: "Dashboard" },
  { to: "/rules", icon: "shield", label: "Rules" },
  { to: "/reports", icon: "description", label: "Reports" },
  { to: "/costs", icon: "account_balance_wallet", label: "Costs" },
];

const pageTitles: Record<string, string> = {
  "/": "Safety Dashboard",
  "/rules": "Rules Manager",
  "/reports": "Daily Report",
  "/costs": "Cost Monitor",
};

const pageDescriptions: Record<string, string> = {
  "/": "Real-time monitoring of AI agent safety events",
  "/rules": "Configure and manage safety evaluation rules",
  "/reports": "Automated daily safety analysis reports",
  "/costs": "Track and optimize AI agent spending",
};

export function Layout() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const title = pageTitles[location.pathname] ?? "BSupervisor";
  const description = pageDescriptions[location.pathname] ?? "";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex w-[15rem] flex-shrink-0 flex-col border-r border-gray-800 bg-gray-900">
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-dark shadow-lg shadow-accent/20">
            <MaterialIcon icon="shield" className="text-lg text-gray-50" filled />
          </div>
          <div>
            <span className="text-sm font-bold text-gray-50">BSupervisor</span>
            <span className="block text-[10px] font-medium tracking-wider text-gray-500 uppercase">
              Safety Platform
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="mx-4 border-t border-gray-800" />

        {/* Nav */}
        <nav className="mt-4 flex flex-1 flex-col gap-0.5 px-3">
          <p className="mb-2 px-3 text-[10px] font-bold tracking-widest text-gray-600 uppercase">
            Monitor
          </p>
          {navItems.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-all duration-150",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-gray-400 hover:bg-gray-850 hover:text-gray-200",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <MaterialIcon
                    icon={icon}
                    className={cn("text-lg", isActive && "text-accent")}
                    filled={isActive}
                  />
                  <span className="flex-1">{label}</span>
                  {isActive && (
                    <MaterialIcon icon="chevron_right" className="text-sm text-accent/60" />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User & Logout */}
        <div className="border-t border-gray-800 px-3 py-3">
          {user && (
            <div className="mb-2 flex items-center gap-2.5 rounded-lg bg-gray-850 px-3 py-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/15">
                <MaterialIcon icon="person" className="text-sm text-accent" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-gray-200">
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
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-gray-500 transition-colors hover:bg-gray-850 hover:text-gray-300"
          >
            <MaterialIcon icon="logout" className="text-lg" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden bg-gray-950">
        {/* Header */}
        <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-gray-800 bg-gray-900/60 px-6 backdrop-blur-md">
          <div>
            <h1 className="text-base font-bold text-gray-50">{title}</h1>
            {description && (
              <p className="text-xs text-gray-500">{description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success-light">
              <span className="h-1.5 w-1.5 rounded-full bg-success-light animate-pulse-dot" />
              System Active
            </span>
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
