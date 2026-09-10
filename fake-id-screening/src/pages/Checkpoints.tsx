import { MapPinned, ArrowDown, Radio } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { checkpointIntel } from "../data/mockData";

export default function Checkpoints() {
  const { chain, message } = checkpointIntel;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Cross-Checkpoint Intelligence</h1>
          <p className="mt-1 text-sm text-ink-muted">Tracks the same identity or document pattern appearing at multiple checkpoints.</p>
        </div>
        <DemoTag />
      </div>

      <Panel className="border-danger/40 bg-danger-bg/30">
        <div className="flex items-center gap-3 p-4">
          <Radio className="animate-pulse text-danger" size={20} />
          <div>
            <p className="text-sm font-semibold text-danger">Intelligence Alert</p>
            <p className="text-xs text-ink-muted">{message}</p>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHeader title="Checkpoint Chain" subtitle="Order of appearance for cluster PB-2291" />
          <div className="flex flex-col items-center gap-2 p-6">
            {chain.map((c, i) => (
              <div key={c.name} className="w-full max-w-sm">
                <div className="flex items-center gap-3 rounded-md border border-base-border2 bg-base-panel2 px-4 py-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-bg text-accent">
                    <MapPinned size={16} />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-ink">{c.name}</p>
                    <p className="text-xs text-ink-faint">{c.city} · Last seen {c.lastSeen}</p>
                  </div>
                  <span className="rounded-full bg-danger/15 px-2 py-1 text-xs font-semibold text-danger">{c.hits} hits</span>
                </div>
                {i !== chain.length - 1 && <ArrowDown className="mx-auto my-2 text-ink-faint" size={18} />}
              </div>
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Pattern Summary" />
          <div className="space-y-3 p-5 text-sm">
            <div className="rounded-md border border-base-border2 bg-base-panel2 p-3">
              <p className="text-ink-faint">Total checkpoints involved</p>
              <p className="mt-1 text-lg font-bold text-ink">{chain.length}</p>
            </div>
            <div className="rounded-md border border-base-border2 bg-base-panel2 p-3">
              <p className="text-ink-faint">Total appearances</p>
              <p className="mt-1 text-lg font-bold text-ink">{chain.reduce((a, c) => a + c.hits, 0)}</p>
            </div>
            <div className="rounded-md border border-base-border2 bg-base-panel2 p-3">
              <p className="text-ink-faint">Recommended action</p>
              <p className="mt-1 font-medium text-warning">Escalate to regional fraud unit</p>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
