import { Shield, Activity, AlertTriangle, FileText, ArrowRight } from "lucide-react";
import { useAuth } from "../lib/auth";

const features = [
  {
    icon: Activity,
    title: "Behavior Logging",
    description: "Track every AI agent action in real-time with structured event capture",
  },
  {
    icon: AlertTriangle,
    title: "Risk Detection",
    description: "Evaluate agent behavior against safety rules and block dangerous actions",
  },
  {
    icon: FileText,
    title: "Daily Reports",
    description: "Automated safety analysis with cost tracking and anomaly summaries",
  },
];

export function Login() {
  const { login } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 px-4">
      {/* Background glow effects */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-1/3 -translate-x-1/2 -translate-y-1/2">
          <div className="h-[500px] w-[500px] rounded-full bg-accent/6 blur-[150px]" />
        </div>
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2">
          <div className="h-[200px] w-[600px] rounded-full bg-accent/3 blur-[100px]" />
        </div>
      </div>

      <div className="relative w-full max-w-md space-y-10">
        {/* Logo & Tagline */}
        <div className="flex flex-col items-center gap-6">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent-dark shadow-2xl shadow-accent/25">
            <Shield className="h-10 w-10 text-gray-50" />
          </div>
          <div className="text-center">
            <h1 className="text-3xl font-bold tracking-tight text-gray-50">
              BSupervisor
            </h1>
            <p className="mt-2 text-base text-gray-400">
              Monitor, audit, and secure your AI agents
            </p>
          </div>
        </div>

        {/* Login card */}
        <div className="rounded-2xl border border-gray-700/50 bg-gray-900/80 p-8 backdrop-blur-sm">
          {/* Feature highlights */}
          <div className="mb-8 space-y-4">
            {features.map((feature) => (
              <div key={feature.title} className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gray-800/80">
                  <feature.icon className="h-5 w-5 text-accent-light" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-200">
                    {feature.title}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-gray-500">
                    {feature.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Divider */}
          <div className="mb-6 border-t border-gray-800" />

          {/* Sign in button */}
          <button
            onClick={login}
            className="group flex w-full items-center justify-center gap-2.5 rounded-xl bg-gradient-to-r from-accent to-accent-dark px-4 py-3.5 text-sm font-semibold text-gray-50 shadow-lg shadow-accent/25 transition-all hover:shadow-accent/40 hover:brightness-110"
          >
            Sign in with BSVibe
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </button>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-600">
          Powered by BSVibe
        </p>
      </div>
    </div>
  );
}
