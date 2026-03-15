"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginUser, registerUser } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthForm() {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Login fields
  const [loginId, setLoginId] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Register fields
  const [regId, setRegId] = useState("");
  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");

  const { login } = useAuth();
  const router = useRouter();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await loginUser({
        user_id: loginId,
        password: loginPassword,
      });
      login(data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(
        msg === "Failed to fetch"
          ? "Cannot reach backend (http://127.0.0.1:8000). Is the server running?"
          : msg,
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await registerUser({
        user_id: regId,
        name: regName,
        email: regEmail,
        password: regPassword,
      });
      // Auto-login after registration
      const data = await loginUser({ user_id: regId, password: regPassword });
      login(data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Registration failed";
      setError(
        msg === "Failed to fetch"
          ? "Cannot reach backend (http://127.0.0.1:8000). Is the server running?"
          : msg,
      );
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "w-full bg-[#0d0d0d] border border-[#2a2a2a] rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-[#c8f135]/60 focus:ring-1 focus:ring-[#c8f135]/20 transition-colors";

  return (
    <div className="w-full max-w-md mx-auto">
      {/* Tab toggles */}
      <div className="flex rounded-xl bg-[#161616] border border-[#2a2a2a] p-1 mb-6">
        {(["login", "register"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setError("");
            }}
            className={`flex-1 py-2 rounded-lg text-sm font-mono font-medium transition-all ${
              tab === t
                ? "bg-[#c8f135] text-black"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "login" ? "Login" : "Register"}
          </button>
        ))}
      </div>

      {tab === "login" ? (
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Roll Number
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="2105085"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Password
            </label>
            <input
              type="password"
              className={inputClass}
              placeholder="••••••••"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 w-full bg-[#c8f135] text-black font-mono font-bold py-2.5 rounded-lg hover:bg-[#d4f84d] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Logging in…" : "Login →"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleRegister} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Roll Number
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="2105085"
              value={regId}
              onChange={(e) => setRegId(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Full Name
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="Suprio Paul"
              value={regName}
              onChange={(e) => setRegName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Email
            </label>
            <input
              type="email"
              className={inputClass}
              placeholder="2105085@cse.buet.ac.bd"
              value={regEmail}
              onChange={(e) => setRegEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Password
            </label>
            <input
              type="password"
              className={inputClass}
              placeholder="••••••••"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 w-full bg-[#c8f135] text-black font-mono font-bold py-2.5 rounded-lg hover:bg-[#d4f84d] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Creating account…" : "Create Account →"}
          </button>
        </form>
      )}
    </div>
  );
}
