"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/src/hooks/useAuth";
import { Layout } from "@/src/components/Layout";
import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
      </div>
    );
  }

  if (!user) {
    // useEffect will redirect; render nothing while redirect is in flight
    return null;
  }

  return <Layout>{children}</Layout>;
}
