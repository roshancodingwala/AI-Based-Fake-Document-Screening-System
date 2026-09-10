import { useEffect, useState } from "react";
import { FlaskConical, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { selfTestHistory as mockHistory } from "../data/mockData";
import { apiRequest } from "../lib/utils";

const manipulationTypes = [
  "Photo Replacement",
  "Font Substitution",
  "MRZ Tampering",
  "Hologram Spoof",
  "Digital Re-scan Artefact",
  "Signature Forgery",
];

interface TestHistoryUI {
  id: string;
  testType: string;
  detected: boolean;
  confidence: number;
  date: string;
}

export default function SelfTest() {
  const [selected, setSelected] = useState(manipulationTypes[0]);
  const [result, setResult] = useState<{ detected: boolean; confidence: number } | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<TestHistoryUI[]>(mockHistory);
  const [isLive, setIsLive] = useState(false);

  const loadHistory = async () => {
    try {
      const data = await apiRequest<any[]>("/api/ai/self-test/history");
      if (Array.isArray(data) && data.length > 0) {
        const mapped: TestHistoryUI[] = data.map((item) => ({
          id: item.test_id,
          testType: item.manipulation_type,
          detected: item.predicted_detection,
          confidence: Math.round(item.confidence * 10) / 10,
          date: typeof item.created_at === "string" ? item.created_at.slice(0, 10) : "Today",
        }));
        setHistory(mapped);
        setIsLive(true);
      }
    } catch (e) {
      // Keep mock fallback
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const runTest = async () => {
    setRunning(true);
    setResult(null);
    try {
      const resp = await apiRequest<any>("/api/ai/self-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manipulation_type: selected,
          test_document_id: "synthetic-test-set-4",
        }),
      });

      setResult({
        detected: resp.predicted_detection,
        confidence: resp.confidence,
      });
      setIsLive(true);
      await loadHistory();
    } catch (err) {
      // Fallback to local simulation if offline
      setTimeout(() => {
        setResult({
          detected: selected !== "Hologram Spoof",
          confidence: selected === "Hologram Spoof" ? 54.1 : Math.round((90 + Math.random() * 9) * 10) / 10,
        });
      }, 600);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Self-Testing AI</h1>
          <p className="mt-1 text-sm text-ink-muted">Run controlled manipulation tests to validate detector performance.</p>
        </div>
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="rounded-md border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
              ● Live AI API Connected
            </span>
          )}
          <DemoTag />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel>
          <PanelHeader title="Run New Test" />
          <div className="space-y-4 p-5">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Test Document</label>
              <div className="rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-sm text-ink">
                Sample Passport — Synthetic Test Set #4
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Manipulation Type</label>
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="w-full rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
              >
                {manipulationTypes.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <button
              onClick={runTest}
              disabled={running}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-accent py-2.5 text-sm font-semibold text-base hover:bg-accent-dim disabled:opacity-50"
            >
              {running ? <Loader2 className="animate-spin" size={16} /> : <FlaskConical size={15} />}
              {running ? "Running AI Test..." : "Run Test"}
            </button>

            {result && (
              <div className={`rounded-md border p-4 text-center ${result.detected ? "border-success/40 bg-success/10" : "border-danger/40 bg-danger/10"}`}>
                <p className="mb-1 text-xs uppercase tracking-wide text-ink-faint">AI Result</p>
                <p className={`flex items-center justify-center gap-2 text-lg font-bold ${result.detected ? "text-success" : "text-danger"}`}>
                  {result.detected ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
                  {result.detected ? "Detected" : "Not Detected"}
                </p>
                <p className="mt-1 text-xs text-ink-muted">Confidence: {result.confidence.toFixed(1)}%</p>
              </div>
            )}
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader title="Test History" subtitle={`Most recent ${history.length} self-test runs`} />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-base-border text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-5 py-3 font-medium">Test ID</th>
                  <th className="px-5 py-3 font-medium">Manipulation Type</th>
                  <th className="px-5 py-3 font-medium">AI Result</th>
                  <th className="px-5 py-3 font-medium">Confidence</th>
                  <th className="px-5 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id} className="border-b border-base-border/60 last:border-0 hover:bg-base-panel2/60">
                    <td className="px-5 py-3 font-mono text-xs text-ink-muted">{t.id}</td>
                    <td className="px-5 py-3 text-ink">{t.testType}</td>
                    <td className="px-5 py-3">
                      <span className={`flex items-center gap-1.5 text-xs font-semibold ${t.detected ? "text-success" : "text-danger"}`}>
                        {t.detected ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                        {t.detected ? "Detected" : "Missed"}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-mono text-ink-muted">{t.confidence}%</td>
                    <td className="px-5 py-3 text-xs text-ink-faint">{t.date}</td>
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
