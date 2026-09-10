import { useEffect, useState } from "react";
import { User, FileText, Network, Building2, FolderOpen } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { fraudNetwork as mockNetwork } from "../data/mockData";
import { apiRequest } from "../lib/utils";

const nodePositions: Record<string, { x: number; y: number }> = {
  personA: { x: 90, y: 60 },
  passA: { x: 90, y: 170 },
  pattern: { x: 320, y: 170 },
  passB: { x: 550, y: 170 },
  personB: { x: 550, y: 60 },
  checkpoint1: { x: 90, y: 290 },
  checkpoint2: { x: 550, y: 290 },
  case1: { x: 320, y: 290 },
};

const iconFor: Record<string, any> = {
  person: User,
  document: FileText,
  pattern: Network,
  checkpoint: Building2,
  case: FolderOpen,
};

const colorFor: Record<string, string> = {
  person: "#4DA3E0",
  document: "#E8A93B",
  pattern: "#F0495A",
  checkpoint: "#2AC7B8",
  case: "#C084FC",
};

export default function FraudNetwork() {
  const [data, setData] = useState(mockNetwork);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function loadNetwork() {
      try {
        const res = await apiRequest<any>("/api/fraud/network/IDN-RS001");
        if (mounted && res && res.connected_cases !== undefined) {
          setData((prev) => ({
            ...prev,
            connectedCases: res.connected_cases || prev.connectedCases,
            commonPattern: res.common_pattern || prev.commonPattern,
            checkpointsInvolved: res.checkpoints_involved?.length ? res.checkpoints_involved : prev.checkpointsInvolved,
          }));
          setIsLive(true);
        }
      } catch (err) {
        // Fallback silently
      }
    }
    loadNetwork();
    return () => {
      mounted = false;
    };
  }, []);

  const { connectedCases, commonPattern, suspiciousSource, checkpointsInvolved, nodes, edges } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Fraud Network Analysis</h1>
          <p className="mt-1 text-sm text-ink-muted">Relationship graph linking documents, identities and checkpoints.</p>
        </div>
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="rounded-md border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
              ● Live Network Engine Connected
            </span>
          )}
          <DemoTag />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Panel className="p-4">
          <p className="text-xs uppercase tracking-wide text-ink-faint">Connected Cases</p>
          <p className="mt-2 text-2xl font-bold text-danger">{connectedCases}</p>
        </Panel>
        <Panel className="p-4 md:col-span-1">
          <p className="text-xs uppercase tracking-wide text-ink-faint">Common Pattern</p>
          <p className="mt-2 text-sm font-medium text-ink">{commonPattern}</p>
        </Panel>
        <Panel className="p-4 md:col-span-1">
          <p className="text-xs uppercase tracking-wide text-ink-faint">Suspicious Source</p>
          <p className="mt-2 text-sm font-medium text-ink">{suspiciousSource}</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-xs uppercase tracking-wide text-ink-faint">Checkpoints Involved</p>
          <p className="mt-2 text-sm font-medium text-ink">{checkpointsInvolved.join(", ")}</p>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Relationship Graph" subtitle="Nodes: person, document, pattern, checkpoint, case" />
        <div className="overflow-x-auto p-5">
          <svg viewBox="0 0 660 360" className="min-w-[640px]" width="100%" height="380">
            {edges.map(([from, to], i) => {
              const a = nodePositions[from];
              const b = nodePositions[to];
              return (
                <line
                  key={i}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="#2C3B5C"
                  strokeWidth={1.5}
                />
              );
            })}
            {nodes.map((n) => {
              const pos = nodePositions[n.id];
              const color = colorFor[n.type];
              return (
                <g key={n.id} transform={`translate(${pos.x}, ${pos.y})`}>
                  <circle r={26} fill={color + "22"} stroke={color} strokeWidth={2} />
                  <text textAnchor="middle" dy={5} fontSize={10} fontWeight={700} fill={color}>
                    {n.type === "person" ? "P" : n.type === "document" ? "D" : n.type === "checkpoint" ? "C" : n.type === "case" ? "#" : "!"}
                  </text>
                  <text textAnchor="middle" dy={45} fontSize={11} fill="#E7ECF5" fontWeight={500}>
                    {n.label.length > 20 ? n.label.slice(0, 20) + "…" : n.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="flex flex-wrap gap-4 border-t border-base-border px-5 py-3 text-xs text-ink-muted">
          {Object.entries(colorFor).map(([type, color]) => {
            const Icon = iconFor[type];
            return (
              <span key={type} className="flex items-center gap-1.5">
                <Icon size={13} style={{ color }} />
                <span className="capitalize">{type}</span>
              </span>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
