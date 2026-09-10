import { Users2, FileWarning, Ban, Clock, Share2, MapPinned } from "lucide-react";
import { Panel, DemoTag } from "../components/Common";
import { alerts } from "../data/mockData";

const iconMap: Record<string, any> = {
  "Multiple Identity Detected": Users2,
  "Possible Document Tampering": FileWarning,
  "Blacklisted Document": Ban,
  "Expired Document": Clock,
  "Fraud Pattern Match": Share2,
  "Cross-Checkpoint Alert": MapPinned,
};

const severityStyle: Record<string, string> = {
  critical: "border-danger/40 bg-danger/10 text-danger",
  high: "border-warning/40 bg-warning/10 text-warning",
  medium: "border-info/40 bg-info/10 text-info",
};

const dotStyle: Record<string, string> = {
  critical: "bg-danger",
  high: "bg-warning",
  medium: "bg-info",
};

export default function Alerts() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Alert Center</h1>
          <p className="mt-1 text-sm text-ink-muted">Active alerts requiring officer attention, most recent first.</p>
        </div>
        <DemoTag />
      </div>

      <div className="space-y-3">
        {alerts.map((a) => {
          const Icon = iconMap[a.title] ?? FileWarning;
          return (
            <Panel key={a.id} className={`border ${severityStyle[a.severity]}`}>
              <div className="flex items-start gap-4 p-4">
                <span className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${dotStyle[a.severity]}`} />
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-base-panel2">
                  <Icon size={16} className="text-ink-muted" />
                </div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-ink">{a.title}</p>
                    <span className="font-mono text-[11px] text-ink-faint">{a.id}</span>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">{a.detail}</p>
                </div>
                <span className="shrink-0 text-xs text-ink-faint">{a.time}</span>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
