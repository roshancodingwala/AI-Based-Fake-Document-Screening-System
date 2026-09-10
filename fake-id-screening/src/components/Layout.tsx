import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  ScanLine,
  FileSearch,
  UserSearch,
  Share2,
  Fingerprint,
  History,
  MapPinned,
  BellRing,
  ShieldCheck,
  FileBarChart,
  Settings,
  ShieldAlert,
  Search,
  ChevronDown,
  Sun,
  Moon,
} from "lucide-react";
import { officer } from "../data/mockData";
import { cn } from "../lib/utils";
import { useTheme } from "../lib/ThemeContext";

const nav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/screening", label: "Document Screening", icon: ScanLine },
  { to: "/results", label: "Verification Results", icon: FileSearch },
  { to: "/identity", label: "Identity Investigation", icon: UserSearch },
  { to: "/fraud-network", label: "Fraud Network", icon: Share2 },
  { to: "/document-dna", label: "Document DNA", icon: Fingerprint },
  { to: "/history", label: "Document History", icon: History },
  { to: "/checkpoints", label: "Cross-Checkpoint Intelligence", icon: MapPinned },
  { to: "/alerts", label: "Alerts", icon: BellRing },
  { to: "/blockchain", label: "Audit", icon: ShieldCheck },
  { to: "/self-test", label: "Self-Testing AI", icon: ShieldAlert },
  { to: "/reports", label: "Reports", icon: FileBarChart },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  return (
    <div className="flex h-screen w-full overflow-hidden bg-base text-ink">
      <aside className="flex w-64 shrink-0 flex-col border-r border-base-border bg-base-panel">
        <div className="flex items-center gap-2.5 border-b border-base-border px-5 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent-bg text-accent">
            <ShieldCheck size={20} strokeWidth={2.2} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight text-ink">SENTRY-ID</div>
            <div className="text-[11px] text-ink-faint">Border Screening Platform</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
                  isActive
                    ? "bg-accent-bg text-accent"
                    : "text-ink-muted hover:bg-base-panel2 hover:text-ink"
                )
              }
            >
              <item.icon size={17} strokeWidth={2} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-base-border p-3">
          <div className="flex items-center gap-2 rounded-md bg-base-panel2 px-3 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent">
              PN
            </div>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-xs font-semibold text-ink">{officer.name}</div>
              <div className="truncate text-[11px] text-ink-faint">{officer.id}</div>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-base-border bg-base-panel px-6">
          <div className="flex items-center gap-2 text-ink-faint">
            <Search size={16} />
            <input
              placeholder="Search document no., name, case ID..."
              className="w-80 bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              System Online
            </span>
            <button className="relative text-ink-muted hover:text-ink">
              <BellRing size={18} />
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white">
                6
              </span>
            </button>
            {/* ── Theme toggle ── */}
            <button
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              className="flex items-center gap-1.5 rounded-full border border-base-border bg-base-panel2 px-3 py-1.5 text-[12px] font-medium text-ink-muted hover:border-accent/50 hover:text-ink transition-colors"
            >
              {theme === "dark" ? (
                <><Sun size={14} className="text-warning" /><span>Light</span></>
              ) : (
                <><Moon size={14} className="text-accent" /><span>Dark</span></>
              )}
            </button>
            <div className="flex items-center gap-2 border-l border-base-border pl-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent">
                PN
              </div>
              <div className="leading-tight">
                <div className="text-xs font-semibold text-ink">{officer.name}</div>
                <div className="text-[11px] text-ink-faint">{officer.post}</div>
              </div>
              <ChevronDown size={14} className="text-ink-faint" />
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-6 py-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
