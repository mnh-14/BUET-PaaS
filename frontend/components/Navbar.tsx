"use client";

import Link from "next/link";
import { useAuth } from "@/context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <nav className="sticky top-0 z-50 border-b border-[#2a2a2a] bg-[#0d0d0d]/90 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-14">
        <Link
          href={user ? "/dashboard" : "/"}
          className="font-mono font-bold text-[#c8f135] text-lg tracking-tight"
        >
          BUET-PaaS
        </Link>

        {user && (
          <div className="flex items-center gap-4">
            <span className="hidden sm:block text-sm text-gray-400 font-mono">
              {user.name}
            </span>
            <span className="text-xs text-[#c8f135] font-mono bg-[#c8f135]/10 px-2.5 py-1 rounded-full border border-[#c8f135]/20">
              ⚡ {user.credit_balance} credits
            </span>
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-gray-100 transition-colors"
            >
              Logout
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
