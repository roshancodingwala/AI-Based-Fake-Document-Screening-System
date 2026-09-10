import { useState, useEffect } from "react";
import { ArrowRight, ScanFace, TriangleAlert, RefreshCw } from "lucide-react";
import { Panel, PanelHeader, DemoTag, RiskBadge } from "../components/Common";
import { identityShadow as mockShadow } from "../data/mockData";
import { apiRequest } from "../lib/utils";

function IdentityCard({
  title,
  name,
  docType,
  docNumber,
  photoLabel,
}: {
  title: string;
  name: string;
  docType: string;
  docNumber: string;
  photoLabel: string;
}) {
  return (
    <Panel className="flex-1">
      <PanelHeader title={title} />
      <div className="flex flex-col items-center gap-3 p-5">
        <div className="flex h-28 w-28 items-center justify-center rounded-full border-2 border-dashed border-base-border2 bg-base-panel2 text-ink-faint">
          <ScanFace size={40} />
        </div>
        <p className="text-[11px] text-ink-faint">{photoLabel}</p>
        <div className="w-full space-y-1.5 pt-2 text-center">
          <p className="text-base font-bold text-ink">{name}</p>
          <p className="font-mono text-xs text-ink-muted">{docType} · {docNumber}</p>
        </div>
      </div>
    </Panel>
  );
}

export default function Identity() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(mockShadow);
  const [isLive, setIsLive] = useState(false);

  const fetchIdentity = async () => {
    setLoading(true);
    try {
      // Query backend identity service
      const searchRes = await apiRequest("/api/identity/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identity_id: "IDN-RS001" }),
      });

      if (searchRes.ok) {
        const searchData = await searchRes.json();
        const topMatch = searchData.matches?.[0];

        // Fetch cross checkpoint history if available
        let history = mockShadow.history;
        try {
          const intelRes = await apiRequest("/api/intelligence/cross-checkpoint/IDN-RS001");
          if (intelRes.ok) {
            const intelData = await intelRes.json();
            if (intelData.history && intelData.history.length > 0) {
              history = intelData.history.map((h: any) => ({
                date: h.timestamp ? h.timestamp.split("T")[0] : "2026-09-05",
                event: `${h.checkpoint_name} (${h.city}) - ${h.notes || "Recorded checkpoint scan"}`,
                risk: (h.risk_level || "low").toLowerCase(),
              }));
            }
          }
        } catch (e) {
          console.warn("Could not fetch cross-checkpoint events:", e);
        }

        if (topMatch) {
          setData({
            current: mockShadow.current,
            related: {
              name: topMatch.name,
              docType: "National ID",
              docNumber: topMatch.identity_id,
              photoLabel: "Archived Biometric Record",
            },
            similarity: Math.round(topMatch.similarity * 1000) / 10,
            status: searchData.possible_multiple_identity ? "Possible Multiple Identity" : "Single Identity Match",
            matchedOn: mockShadow.matchedOn,
            history,
          });
          setIsLive(true);
        }
      }
    } catch (err) {
      console.warn("Using mock shadow data due to API error:", err);
      setData(mockShadow);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIdentity();
  }, []);

  const { current, related, similarity, status, matchedOn, history } = data;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Identity Investigation — Identity Shadow</h1>
          <p className="mt-1 text-sm text-ink-muted">Biometric search for previous or related identities linked to this person.</p>
        </div>
        <div className="flex items-center gap-2">
          {isLive ? (
            <span className="rounded-full bg-accent-bg px-2.5 py-0.5 text-xs font-semibold text-accent border border-accent/30">
              Live Biometric Match
            </span>
          ) : (
            <DemoTag />
          )}
          <button
            onClick={fetchIdentity}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-1.5 text-xs text-ink-muted hover:border-accent hover:text-ink disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-col items-stretch gap-4 lg:flex-row lg:items-center">
        <IdentityCard title="Current Identity" name={current.name} docType={current.docType} docNumber={current.docNumber} photoLabel={current.photoLabel} />

        <div className="flex flex-col items-center gap-2 px-2">
          <ArrowRight className="hidden text-accent lg:block" size={28} />
          <div className="rounded-full border border-accent/40 bg-accent-bg px-4 py-2 text-center">
            <p className="text-2xl font-bold text-accent">{similarity}%</p>
            <p className="text-[10px] uppercase tracking-wide text-accent/80">Similarity</p>
          </div>
          <ArrowRight className="hidden text-accent lg:block" size={28} />
        </div>

        <IdentityCard title="Possible Related Identity" name={related.name} docType={related.docType} docNumber={related.docNumber} photoLabel={related.photoLabel} />
      </div>

      <Panel className="border-danger/40 bg-danger-bg/30">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <TriangleAlert className="text-danger" size={20} />
            <div>
              <p className="text-sm font-semibold text-danger">{status}</p>
              <p className="text-xs text-ink-muted">Face and biometric search found a strong link between these two records — recommend investigation.</p>
            </div>
          </div>
          <RiskBadge level="high" label="Escalated" />
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-1">
          <PanelHeader title="Matched Biometric Signals" />
          <ul className="space-y-2 p-5 text-sm text-ink-muted">
            {matchedOn.map((m) => (
              <li key={m} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                {m}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader title="Cross-Identity Timeline" subtitle="Combined activity of both linked identities" />
          <ul className="space-y-4 p-5">
            {history.map((h, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="w-24 shrink-0 font-mono text-xs text-ink-faint">{h.date}</span>
                <span className="flex-1 text-ink-muted">{h.event}</span>
                <RiskBadge level={h.risk as any} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
