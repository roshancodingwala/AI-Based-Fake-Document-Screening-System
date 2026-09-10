import { Panel, PanelHeader, RiskBadge, DemoTag } from "../components/Common";
import { documentHistory } from "../data/mockData";

export default function DocumentHistory() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Document History</h1>
          <p className="mt-1 text-sm text-ink-muted">Full lifecycle of Passport P123456, from issuance to current verification.</p>
        </div>
        <DemoTag />
      </div>

      <Panel>
        <PanelHeader title="Timeline" subtitle="6 recorded events" />
        <ol className="p-6">
          {documentHistory.map((h, i) => (
            <li key={i} className="relative flex gap-5 pb-8 last:pb-0">
              {i !== documentHistory.length - 1 && (
                <span className="absolute left-[9px] top-6 h-full w-0.5 bg-base-border2" />
              )}
              <span
                className={`z-10 mt-1 h-5 w-5 shrink-0 rounded-full border-4 ${
                  h.risk === "critical"
                    ? "border-[#C084FC] bg-base-panel"
                    : h.risk === "high"
                    ? "border-danger bg-base-panel"
                    : h.risk === "medium"
                    ? "border-warning bg-base-panel"
                    : "border-success bg-base-panel"
                }`}
              />
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-ink">{h.title}</p>
                  <RiskBadge level={h.risk as any} />
                  <span className="font-mono text-xs text-ink-faint">{h.date}</span>
                </div>
                <p className="mt-1 text-sm text-ink-muted">{h.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}
