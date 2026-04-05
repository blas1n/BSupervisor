import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Shield, Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";

export function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleCallback } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // BSVibeAuth.handleCallback() handles hash parsing, state validation, and session storage
    const success = handleCallback();

    if (success) {
      navigate("/", { replace: true });
      return;
    }

    // Error
    const err = searchParams.get("error");
    setError(err || "Authentication failed. No valid token received.");
  }, [handleCallback, searchParams, navigate]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <div className="w-full max-w-sm space-y-6 px-6 text-center">
          <div className="flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/15">
              <Shield className="h-8 w-8 text-accent" />
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-50">
              Authentication Error
            </h2>
            <p className="mt-2 text-sm text-gray-400">{error}</p>
          </div>
          <button
            onClick={() => navigate("/", { replace: true })}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
        <p className="text-sm text-gray-400">Completing sign in...</p>
      </div>
    </div>
  );
}
