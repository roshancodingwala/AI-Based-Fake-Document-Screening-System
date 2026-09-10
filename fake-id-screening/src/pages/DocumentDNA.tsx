import { useState, useEffect } from "react";
import { Fingerprint, RefreshCw } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { documentDNA as mockDNA } from "../data/mockData";
import { getActiveScreeningResult } from "../lib/screeningResult";
import { apiRequest } from "../lib/utils";

export default function DocumentDNA() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(mockDNA);
  const [isLive, setIsLive] = useState(false);
  const [docNumber, setDocNumber] = useState("P123456");

  const fetchDNA = async () => {
    setLoading(true);
    try {
      const activeResult = getActiveScreeningResult();
      const targetDoc = activeResult.document?.docNumber || "P123456";
      setDocNumber(targetDoc);

      const formData = new FormData();
      formData.append("document_number", targetDoc);

      const res = await apiRequest("/api/documents/dna", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const dnaRes = await res.json();
        if (dnaRes.matching_features && dnaRes.matching_features.length > 0) {
          setData({
            matchScore: Math.round(dnaRes.similarity_score),
            summary: dnaRes.summary,
            factors: dnaRes.matching_features.map((f: any) => ({
              name: f.name,
              score: Math.round(f.score),
            })),
            relatedDocuments: (dnaRes.related_documents || []).map((rd: any) => ({
              id: rd.id,
              flaggedOn: rd.flagged_date || "2026-08-14",
              match: Math.round(rd.match_pct),
              notes: rd.notes || "Shared printing pattern",
            })),
          });
          setIsLive(true);
        }
      }
    } catch (err) {
      console.warn("Could not query backend DNA service, using mock data:", err);
      setData(mockDNA);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDNA();
  }, []);

  const { matchScore, summary, factors, relatedDocuments } = data;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Document DNA</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Structural fingerprinting of fonts, layout, print pattern and security features · Target: {docNumber}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isLive ? (
            <span className="rounded-full bg-accent-bg px-2.5 py-0.5 text-xs font-semibold text-accent border border-accent/30">
              Live Fingerprint Analysis
            </span>
          ) : (
            <DemoTag />
          )}
          <button
            onClick={fetchDNA}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-1.5 text-xs text-ink-muted hover:border-accent hover:text-ink disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      <Panel className="border-danger/40 bg-danger-bg/30">
        <div className="flex items-center gap-5 p-5">
          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-4 border-danger/40 bg-base-panel text-danger">
            <Fingerprint size={30} />
          </div>
          <div>
            <p className="text-2xl font-bold text-ink">Document DNA Match: {matchScore}%</p>
            <p className="text-sm text-ink-muted">{summary}</p>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel>
          <PanelHeader title="Structural Comparison Factors" subtitle="Current document vs. flagged reference cluster" />
          <div className="space-y-4 p-5">
            {factors.map((f) => (
              <div key={f.name}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-ink-muted">{f.name}</span>
                  <span className="font-mono font-semibold text-ink">{f.score}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-base-panel2">
                  <div
                    className={`h-full rounded-full ${f.score >= 90 ? "bg-danger" : f.score >= 75 ? "bg-warning" : "bg-success"}`}
                    style={{ width: `${f.score}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Related Flagged Documents" subtitle="Documents sharing this structural fingerprint" />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-base-border text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-5 py-3 font-medium">Document ID</th>
                  <th className="px-5 py-3 font-medium">Flagged On</th>
                  <th className="px-5 py-3 font-medium">Match</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-base-border/50 font-mono text-xs">
                {relatedDocuments.map((doc) => (
                  <tr key={doc.id} className="hover:bg-base-panel2/50">
                    <td className="px-5 py-3 font-medium text-ink">{doc.id}</td>
                    <td className="px-5 py-3 text-ink-muted">{doc.flaggedOn}</td>
                    <td className="px-5 py-3 font-semibold text-danger">{doc.match}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
