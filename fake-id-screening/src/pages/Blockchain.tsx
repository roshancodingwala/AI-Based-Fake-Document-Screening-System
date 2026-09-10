import { useEffect, useState } from "react";
import { Blocks, Link2, ShieldCheck, Loader2 } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { blockchainRecords as mockRecords } from "../data/mockData";
import { apiRequest } from "../lib/utils";

interface BlockchainRecordUI {
  verId: string;
  hash: string;
  timestamp: string;
  result: string;
  status: string;
}

export default function Blockchain() {
  const [records, setRecords] = useState<BlockchainRecordUI[]>(mockRecords);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function fetchRecords() {
      try {
        const data = await apiRequest<any[]>("/api/blockchain/records?limit=10");
        if (mounted && Array.isArray(data) && data.length > 0) {
          const mapped: BlockchainRecordUI[] = data.map((r) => ({
            verId: r.verification_id,
            hash: r.document_hash,
            timestamp: typeof r.timestamp === "string" ? r.timestamp.replace("T", " ").slice(0, 19) : String(r.timestamp),
            result: r.result,
            status: r.status || "CONFIRMED",
          }));
          setRecords(mapped);
          setIsLive(true);
        }
      } catch (e) {
        // Fall back gracefully to mock data
      } finally {
        if (mounted) setLoading(false);
      }
    }
    fetchRecords();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Blockchain Audit</h1>
          <p className="mt-1 text-sm text-ink-muted">Tamper-proof verification records. No personal data is stored on-chain.</p>
        </div>
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="rounded-md border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
              ● Live API Connected
            </span>
          )}
          <DemoTag />
        </div>
      </div>

      <Panel className="border-accent/30 bg-accent-bg/40">
        <div className="flex items-start gap-3 p-4 text-sm text-ink-muted">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-accent" />
          <p>
            Each verification produces a cryptographic hash of the decision outcome only — names, document numbers and photos
            are never written to the chain, and are stored solely in the secure internal case system.
          </p>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Recent Blockchain Records"
          subtitle={loading ? "Loading audit chain..." : `Displaying ${records.length} verification records`}
        />
        {loading ? (
          <div className="flex items-center justify-center py-12 text-ink-muted">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-accent" />
            Loading records from backend...
          </div>
        ) : (
          <div className="divide-y divide-base-border/60">
            {records.map((r) => (
              <div key={r.verId} className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-base-panel2 text-accent">
                    <Blocks size={18} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-ink">Blockchain Record {r.verId}</p>
                    <p className="flex items-center gap-1 font-mono text-xs text-ink-faint">
                      <Link2 size={11} /> {r.hash}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-6 text-xs">
                  <div>
                    <p className="text-ink-faint">Timestamp</p>
                    <p className="font-mono text-ink-muted">{r.timestamp}</p>
                  </div>
                  <div>
                    <p className="text-ink-faint">Result</p>
                    <p className={`font-semibold ${r.result === "VERIFIED" ? "text-success" : "text-danger"}`}>{r.result}</p>
                  </div>
                  <span className="rounded-full border border-success/30 bg-success/10 px-2.5 py-1 font-medium text-success">
                    {r.status} ✓
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
