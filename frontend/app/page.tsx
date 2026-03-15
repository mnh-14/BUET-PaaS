"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import AuthForm from "@/components/AuthForm";

export default function LandingPage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  return (
    <main className="min-h-screen bg-[#0d0d0d] flex flex-col items-center justify-center px-4 py-12">
      {/* Logo / Hero */}
      <div className="mb-10 text-center">
        <span className="font-mono font-bold text-[#c8f135] text-3xl tracking-tight">
          BUET-PaaS
        </span>
        <p className="mt-2 text-sm text-gray-500">
          Deploy your GitHub repositories on BUET infrastructure
        </p>
      </div>

      {/* Auth card */}
      <div className="w-full max-w-md bg-[#161616] border border-[#2a2a2a] rounded-2xl p-8">
        <AuthForm />
      </div>

      <p className="mt-6 text-xs text-gray-600">
        BUET CSE · Platform as a Service
      </p>
    </main>
  );
}
