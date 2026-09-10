import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Lock, User, Eye, EyeOff, Fingerprint } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="relative flex h-screen w-full items-center justify-center overflow-hidden bg-base text-ink">
      <div className="scan-grid pointer-events-none absolute inset-0 opacity-60" />
      <div className="pointer-events-none absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-accent/10 blur-3xl" />

      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-accent-bg text-accent">
            <ShieldCheck size={26} strokeWidth={2.2} />
          </div>
          <h1 className="text-lg font-bold tracking-tight">SENTRY-ID</h1>
          <p className="mt-1 text-xs text-ink-faint">AI-Based Document &amp; Identity Screening Platform</p>
        </div>

        <div className="rounded-lg border border-base-border bg-base-panel p-6 shadow-panel">
          <div className="mb-5 flex items-center gap-2 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-[11px] text-ink-muted">
            <Lock size={13} className="text-accent" />
            Restricted access. Authorized personnel only. All sessions are logged.
          </div>

          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              navigate("/dashboard");
            }}
          >
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Officer ID / Email</label>
              <div className="flex items-center gap-2 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 focus-within:border-accent">
                <User size={15} className="text-ink-faint" />
                <input
                  defaultValue="OFC-20481"
                  className="w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                  placeholder="OFC-00000"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Password</label>
              <div className="flex items-center gap-2 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 focus-within:border-accent">
                <Lock size={15} className="text-ink-faint" />
                <input
                  type={showPassword ? "text" : "password"}
                  defaultValue="••••••••••"
                  className="w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                />
                <button type="button" onClick={() => setShowPassword((s) => !s)} className="text-ink-faint hover:text-ink">
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs">
              <label className="flex items-center gap-2 text-ink-muted">
                <input type="checkbox" defaultChecked className="h-3.5 w-3.5 rounded border-base-border2 bg-base-panel2 accent-accent" />
                Remember me on this device
              </label>
              <button type="button" className="font-medium text-accent hover:underline">
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              className="w-full rounded-md bg-accent py-2.5 text-sm font-semibold text-base transition hover:bg-accent-dim"
            >
              Secure Sign In
            </button>

            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-md border border-base-border2 py-2.5 text-sm font-medium text-ink-muted hover:border-accent hover:text-accent"
              onClick={() => navigate("/dashboard")}
            >
              <Fingerprint size={15} />
              Sign in with biometric key
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-[11px] text-ink-faint">
          v2.4.1 · Prototype build · For evaluation purposes only
        </p>
      </div>
    </div>
  );
}
