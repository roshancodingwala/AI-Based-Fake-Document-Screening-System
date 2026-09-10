import type { ReactNode } from "react";
import { cn, riskColors } from "../lib/utils";

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-lg border border-base-border bg-base-panel", className)}>
      {children}
    </div>
  );
}

export function PanelHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between border-b border-base-border px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function RiskBadge({ level, label }: { level: "low" | "medium" | "high" | "critical"; label?: string }) {
  const c = riskColors(level);
  const text = label ?? level.charAt(0).toUpperCase() + level.slice(1);
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium", c.text, c.bg, c.border)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
      {text}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, "low" | "medium" | "high" | "critical"> = {
    Verified: "low",
    Suspicious: "medium",
    "High Risk": "high",
    Blacklisted: "critical",
    Confirmed: "low",
    VERIFIED: "low",
    FLAGGED: "high",
  };
  return <RiskBadge level={map[status] ?? "medium"} label={status} />;
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  tone?: "default" | "danger" | "warning" | "success" | "accent";
}) {
  const toneMap: Record<string, string> = {
    default: "text-ink",
    danger: "text-danger",
    warning: "text-warning",
    success: "text-success",
    accent: "text-accent",
  };
  return (
    <Panel className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</span>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <div className={cn("mt-2 text-2xl font-bold tabular-nums", toneMap[tone])}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-muted">{hint}</div>}
    </Panel>
  );
}

export function StageIcon({ status }: { status: "completed" | "processing" | "warning" | "failed" | "pending" }) {
  const styles: Record<string, string> = {
    completed: "bg-success/15 border-success text-success",
    processing: "bg-info/15 border-info text-info animate-pulse",
    warning: "bg-warning/15 border-warning text-warning",
    failed: "bg-danger/15 border-danger text-danger",
    pending: "bg-base-panel2 border-base-border2 text-ink-faint",
  };
  const symbol: Record<string, string> = {
    completed: "✓",
    processing: "…",
    warning: "!",
    failed: "✕",
    pending: "•",
  };
  return (
    <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-sm font-bold", styles[status])}>
      {symbol[status]}
    </div>
  );
}

export function DemoTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-accent/30 bg-accent-bg px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent">
      Demo / Simulated
    </span>
  );
}
