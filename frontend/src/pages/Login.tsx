import { Shield, ArrowRight } from "lucide-react";
import { useAuth } from "../lib/auth";

export function Login() {
  const { login } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950">
      {/* Background decoration */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-1/3 -translate-x-1/2 -translate-y-1/2">
          <div className="h-[400px] w-[400px] rounded-full bg-accent/5 blur-[120px]" />
        </div>
      </div>

      <div className="relative w-full max-w-sm space-y-8 px-6">
        {/* Logo */}
        <div className="flex flex-col items-center gap-5">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent-dark shadow-2xl shadow-accent/25">
            <Shield className="h-10 w-10 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-gray-50">
              BSupervisor
            </h1>
            <p className="mt-1.5 text-sm text-gray-400">
              AI Agent Safety & Auditing Platform
            </p>
          </div>
        </div>

        {/* Login card */}
        <div className="rounded-2xl border border-gray-800 bg-gray-900/80 p-8 backdrop-blur-sm">
          <div className="mb-6 text-center">
            <p className="text-sm font-medium text-gray-300">
              Welcome back
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Sign in to access the safety dashboard
            </p>
          </div>
          <button
            onClick={login}
            className="group flex w-full items-center justify-center gap-2.5 rounded-xl bg-gradient-to-r from-accent to-accent-dark px-4 py-3.5 text-sm font-semibold text-white shadow-lg shadow-accent/25 transition-all hover:shadow-accent/40 hover:brightness-110"
          >
            Sign in with BSVibe
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </button>
        </div>

        <p className="text-center text-[11px] text-gray-600">
          Protected by BSVibe Authentication
        </p>
      </div>
    </div>
  );
}
