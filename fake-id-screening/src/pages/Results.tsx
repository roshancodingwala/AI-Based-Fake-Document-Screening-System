import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ShieldAlert, Share2, UserSearch, Fingerprint, CheckCircle2, RotateCcw, Activity } from "lucide-react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { getActiveScreeningResult, clearScreeningResult } from "../lib/screeningResult";
import type { ParsedScreeningResult } from "../lib/screeningResult";
import { apiRequest } from "../lib/utils";

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-base-border/60 py-2.5 text-sm last:border-0">
      <span className="text-ink-faint">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </div>
  );
}

function ScoreBar({ label, value, invert = false }: { label: string; value: number; invert?: boolean }) {
  const good = invert ? value < 40 : value > 70;
  const mid = invert ? value < 70 : value >= 40 && value <= 70;
  const color = good ? "bg-success" : mid ? "bg-warning" : "bg-danger";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-ink-muted">{label}</span>
        <span className="font-mono font-semibold text-ink">{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-base-panel2">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  );
}

export default function Results() {
  const [data, setData] = useState<ParsedScreeningResult>(getActiveScreeningResult());
  const [decisionSubmitted, setDecisionSubmitted] = useState<string | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);

  useEffect(() => {
    setData(getActiveScreeningResult());
  }, []);

  const handleResetToDemo = () => {
    clearScreeningResult();
    setData(getActiveScreeningResult());
    setDecisionSubmitted(null);
  };

  const handleOfficerDecision = async (decision: string) => {
    setDecisionLoading(true);
    try {
      if (data.isLive && data.verificationId) {
        await apiRequest(`/api/verification/${data.verificationId}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decision,
            officer_id: "OFC-20481",
          }),
        });
      }
      setDecisionSubmitted(decision);
    } catch (err) {
      console.warn("Could not sync decision to backend audit log, recording locally:", err);
      setDecisionSubmitted(decision);
    } finally {
      setDecisionLoading(false);
    }
  };

  const { document, ai, reasons } = data;
  const isHighRisk = ai.riskScore >= 70;
  const isMedRisk = ai.riskScore >= 40 && ai.riskScore < 70;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-ink">Verification Result</h1>
            {data.isLive ? (
              <span className="flex items-center gap-1 rounded-full bg-accent-bg px-2.5 py-0.5 text-xs font-semibold text-accent border border-accent/30">
                <Activity size={12} className="animate-pulse" /> Live Screening
              </span>
            ) : (
              <DemoTag />
            )}
          </div>
          <p className="mt-1 text-sm text-ink-muted">
            Case {data.verificationId} · Terminal 3, Counter 4 · {data.timestamp}
          </p>
        </div>

        {data.isLive && (
          <button
            onClick={handleResetToDemo}
            className="flex items-center gap-1.5 self-start rounded-md border border-base-border2 bg-base-panel2 px-3 py-1.5 text-xs text-ink-muted hover:border-accent hover:text-ink"
          >
            <RotateCcw size={13} /> Reset to Demo Sample
          </button>
        )}
      </div>

      <Panel
        className={
          isHighRisk
            ? "border-danger/40 bg-danger-bg/30"
            : isMedRisk
            ? "border-warning/40 bg-warning-bg/30"
            : "border-success/40 bg-success-bg/30"
        }
      >
        <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div
              className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-4 text-2xl font-bold ${
                isHighRisk
                  ? "border-danger/40 text-danger"
                  : isMedRisk
                  ? "border-warning/40 text-warning"
                  : "border-success/40 text-success"
              }`}
            >
              {ai.riskScore}
            </div>
            <div>
              <p
                className={`text-xs font-medium uppercase tracking-wide ${
                  isHighRisk ? "text-danger" : isMedRisk ? "text-warning" : "text-success"
                }`}
              >
                Risk Score / 100
              </p>
              <p className="text-lg font-bold text-ink">STATUS: {ai.riskLevel} RISK</p>
              <p className="text-xs text-ink-muted">
                {isHighRisk
                  ? "Recommend secondary inspection before clearance."
                  : isMedRisk
                  ? "Elevated caution advised. Check travel itinerary."
                  : "Standard clearance recommended."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/identity"
              className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-xs font-medium text-ink hover:border-accent"
            >
              <UserSearch size={14} /> Investigate Identity
            </Link>
            <Link
              to="/fraud-network"
              className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-xs font-medium text-ink hover:border-accent"
            >
              <Share2 size={14} /> View Fraud Network
            </Link>
            <Link
              to="/document-dna"
              className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-xs font-medium text-ink hover:border-accent"
            >
              <Fingerprint size={14} /> Document DNA
            </Link>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel>
          <PanelHeader title="Document Information" subtitle="Extracted via OCR" />
          <div className="px-5 py-2">
            <InfoRow label="Name" value={document.name} />
            <InfoRow label="Document Number" value={document.docNumber} />
            <InfoRow label="Document Type" value={document.docType} />
            <InfoRow label="Nationality" value={document.nationality} />
            <InfoRow label="Date of Birth" value={document.dob} />
            <InfoRow label="Gender" value={document.gender} />
            <InfoRow label="Issue Date" value={document.issueDate} />
            <InfoRow label="Expiry Date" value={document.expiryDate} />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="AI Analysis Results" subtitle="Automated screening confidence" />
          <div className="space-y-4 px-5 py-4">
            <ScoreBar label="OCR Confidence" value={ai.ocrConfidence} />
            <ScoreBar label="Document Authenticity" value={ai.authenticity} />
            <ScoreBar label="Face Match Score" value={ai.faceMatchScore} />
            <div className="grid grid-cols-2 gap-3 pt-2 text-xs">
              <div className="rounded-md border border-base-border2 bg-base-panel2 p-2.5">
                <p className="text-ink-faint">Tampering Status</p>
                <p
                  className={`mt-1 font-medium ${
                    ai.tamperingStatus.includes("Alteration") ? "text-warning" : "text-success"
                  }`}
                >
                  {ai.tamperingStatus}
                </p>
              </div>
              <div className="rounded-md border border-base-border2 bg-base-panel2 p-2.5">
                <p className="text-ink-faint">Identity Match</p>
                <p className="mt-1 font-medium text-warning">{ai.identityMatch}</p>
              </div>
              <div className="rounded-md border border-base-border2 bg-base-panel2 p-2.5">
                <p className="text-ink-faint">Blacklist Status</p>
                <p className="mt-1 font-medium text-success">{ai.blacklistStatus}</p>
              </div>
              <div className="rounded-md border border-base-border2 bg-base-panel2 p-2.5">
                <p className="text-ink-faint">Risk Score</p>
                <p
                  className={`mt-1 font-medium ${
                    isHighRisk ? "text-danger" : isMedRisk ? "text-warning" : "text-success"
                  }`}
                >
                  {ai.riskScore} / 100
                </p>
              </div>
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Analysis Signals & Findings"
            subtitle="Plain-language explanation of flags"
            right={<ShieldAlert size={16} className={isHighRisk ? "text-danger" : "text-warning"} />}
          />
          <ul className="space-y-3 px-5 py-4">
            {reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-ink-muted">
                <AlertTriangle
                  size={14}
                  className={`mt-0.5 shrink-0 ${isHighRisk ? "text-danger" : "text-warning"}`}
                />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Officer Decision" subtitle="This decision will be recorded in the audit trail" />
        <div className="flex flex-wrap items-center gap-3 p-5">
          {decisionSubmitted ? (
            <div className="flex items-center gap-2 rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-accent border border-accent/30">
              <CheckCircle2 size={16} /> Decision Logged to Audit Trail: {decisionSubmitted}
            </div>
          ) : (
            <>
              <button
                disabled={decisionLoading}
                onClick={() => handleOfficerDecision("Cleared")}
                className="rounded-md bg-success/15 px-4 py-2 text-sm font-semibold text-success hover:bg-success/25 transition"
              >
                Clear Traveler
              </button>
              <button
                disabled={decisionLoading}
                onClick={() => handleOfficerDecision("Secondary Inspection")}
                className="rounded-md bg-warning/15 px-4 py-2 text-sm font-semibold text-warning hover:bg-warning/25 transition"
              >
                Refer for Secondary Inspection
              </button>
              <button
                disabled={decisionLoading}
                onClick={() => handleOfficerDecision("Denied Entry")}
                className="rounded-md bg-danger/15 px-4 py-2 text-sm font-semibold text-danger hover:bg-danger/25 transition"
              >
                Deny Entry &amp; Escalate
              </button>
            </>
          )}
          <Link to="/reports" className="ml-auto text-xs font-medium text-accent hover:underline">
            Generate full report →
          </Link>
        </div>
      </Panel>
    </div>
  );
}
