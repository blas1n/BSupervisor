import { Outlet, NavLink, useLocation } from "react-router-dom";
import { cn } from "../lib/utils";
import { useAuth } from "../lib/auth";
import { MaterialIcon } from "../components/MaterialIcon";

const navItems = [
  { to: "/", icon: "dashboard", label: "Dashboard" },
  { to: "/rules", icon: "gavel", label: "Rules" },
  { to: "/reports", icon: "description", label: "Reports" },
  { to: "/costs", icon: "payments", label: "Costs" },
];

const pageTitles: Record<string, string> = {
  "/": "Safety Dashboard",
  "/rules": "Rules Manager",
  "/reports": "Daily Report",
  "/costs": "Cost Monitor",
};


export function Layout() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const title = pageTitles[location.pathname] ?? "BSupervisor";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex w-64 flex-shrink-0 flex-col bg-gray-950">
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 py-6">
          <MaterialIcon icon="security" className="text-2xl text-accent" filled />
          <div>
            <span className="text-base font-black text-accent tracking-tighter uppercase">BSupervisor</span>
            <span className="block text-[10px] font-bold tracking-widest text-gray-500 uppercase">
              AI Safety Platform
            </span>
          </div>
        </div>

        {/* Nav */}
        <nav className="mt-4 flex flex-1 flex-col gap-1 px-4">
          {navItems.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-4 px-4 py-3 text-sm uppercase font-bold tracking-tight transition-colors duration-200",
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
        <header className="flex h-16 flex-shrink-0 items-center justify-between bg-gray-950/80 px-8 backdrop-blur-md sticky top-0 z-40">
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-400 uppercase tracking-widest font-bold">
              {title}
            </span>
          </div>
          <div className="flex items-center gap-6">
            <MaterialIcon icon="notifications" className="text-gray-400 hover:text-gray-50 cursor-pointer transition-opacity" />
            <MaterialIcon icon="settings" className="text-gray-400 hover:text-gray-50 cursor-pointer transition-opacity" />
            <div className="h-8 w-8 rounded-lg bg-gray-800 flex items-center justify-center">
              <MaterialIcon icon="person" className="text-sm text-gray-400" />
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
