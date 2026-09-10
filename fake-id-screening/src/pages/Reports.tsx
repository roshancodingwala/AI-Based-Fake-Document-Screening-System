import { useState, useEffect } from "react";
import { Printer, Download, FileOutput, Activity } from "lucide-react";
import { Panel, DemoTag, StatusPill } from "../components/Common";
import { identityShadow, fraudNetwork, officer } from "../data/mockData";
import { getActiveScreeningResult } from "../lib/screeningResult";
import type { ParsedScreeningResult } from "../lib/screeningResult";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-base-border/60 px-6 py-5 last:border-0">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-faint">{title}</h3>
      {children}
    </div>
  );
}

export default function Reports() {
  const [data, setData] = useState<ParsedScreeningResult>(getActiveScreeningResult());

  useEffect(() => {
    setData(getActiveScreeningResult());
  }, []);

  const { document, ai, reasons } = data;

  const handlePrint = () => {
    window.print();
  };

  const handleDownload = () => {
    const reportText = `SENTRY-ID VERIFICATION REPORT
=============================
Case: ${data.verificationId}
Generated: ${data.timestamp}
Officer: ${officer.name} (${officer.id})
Status: ${ai.riskLevel} RISK (${ai.riskScore}/100)

TRAVELER DETAILS
Name: ${document.name}
Document: ${document.docType} ${document.docNumber}
Nationality: ${document.nationality}
DOB: ${document.dob}

AI & BIOMETRIC SIGNALS
OCR Confidence: ${ai.ocrConfidence}%
Authenticity: ${ai.authenticity}%
Tampering: ${ai.tamperingStatus}
Face Match: ${ai.faceMatchScore}%
Identity Match: ${ai.identityMatch}

FINDINGS
${reasons.map((r, i) => `${i + 1}. ${r}`).join("\n")}
`;
    const blob = new Blob([reportText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement("a");
    a.href = url;
    a.download = `sentry-report-${data.verificationId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-ink">Verification Report</h1>
            {data.isLive ? (
              <span className="flex items-center gap-1 rounded-full bg-accent-bg px-2.5 py-0.5 text-xs font-semibold text-accent border border-accent/30">
                <Activity size={12} className="animate-pulse" /> Live Case
              </span>
            ) : (
              <DemoTag />
            )}
          </div>
          <p className="mt-1 text-sm text-ink-muted">Case {data.verificationId} · Ready for export</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrint}
            className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-xs font-medium text-ink hover:border-accent"
          >
            <Printer size={14} /> Print
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-xs font-medium text-ink hover:border-accent"
          >
            <Download size={14} /> Download
          </button>
          <button
            onClick={handlePrint}
            className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-semibold text-base hover:bg-accent-dim"
          >
            <FileOutput size={14} /> Export PDF
          </button>
        </div>
      </div>

      <Panel>
        <div className="flex items-center justify-between border-b border-base-border px-6 py-4">
          <div>
            <p className="text-sm font-bold text-ink">SENTRY-ID Official Verification Report</p>
            <p className="text-xs text-ink-faint">Generated {data.timestamp} by {officer.name} ({officer.id})</p>
          </div>
          <StatusPill status={ai.riskLevel === "HIGH" ? "High Risk" : ai.riskLevel === "MEDIUM" ? "Medium Risk" : "Low Risk"} />
        </div>

        <Section title="Document Information">
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm md:grid-cols-4">
            <div><p className="text-ink-faint">Name</p><p className="font-medium text-ink">{document.name}</p></div>
            <div><p className="text-ink-faint">Document No.</p><p className="font-mono font-medium text-ink">{document.docNumber}</p></div>
            <div><p className="text-ink-faint">Nationality</p><p className="font-medium text-ink">{document.nationality}</p></div>
            <div><p className="text-ink-faint">DOB</p><p className="font-medium text-ink">{document.dob}</p></div>
          </div>
        </Section>

        <Section title="AI Analysis">
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm md:grid-cols-4">
            <div><p className="text-ink-faint">OCR Confidence</p><p className="font-medium text-ink">{ai.ocrConfidence}%</p></div>
            <div><p className="text-ink-faint">Authenticity</p><p className="font-medium text-warning">{ai.authenticity}%</p></div>
            <div><p className="text-ink-faint">Tampering</p><p className="font-medium text-warning">{ai.tamperingStatus}</p></div>
            <div><p className="text-ink-faint">Risk Score</p><p className="font-medium text-danger">{ai.riskScore}/100</p></div>
          </div>
        </Section>

        <Section title="Face Verification">
          <p className="text-sm text-ink-muted">
            Face match score of <span className="font-medium text-ink">{ai.faceMatchScore}%</span> against the submitted document photo.
            {ai.faceMatchScore < 85 ? " Score indicates potential photo substitution or low image fidelity." : " Face match satisfies threshold."}
          </p>
        </Section>

        <Section title="Identity History">
          <p className="text-sm text-ink-muted">
            Biometric cross-matching: linked to archived identity <span className="font-medium text-ink">{identityShadow.related.name}</span> ({identityShadow.related.docNumber}) with {identityShadow.similarity}% biometric similarity.
          </p>
        </Section>

        <Section title="Fraud Connections">
          <p className="text-sm text-ink-muted">
            Part of a network of {fraudNetwork.connectedCases} connected cases sharing pattern: {fraudNetwork.commonPattern}.
          </p>
        </Section>

        <Section title="Risk Score & Reasoning">
          <p className="mb-2 text-sm font-semibold text-danger">{ai.riskScore}/100 — {ai.riskLevel} RISK</p>
          <ul className="list-inside list-disc space-y-1 text-sm text-ink-muted">
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Section>

        <Section title="Audit Record">
          <p className="font-mono text-xs text-ink-faint">Case Ref: {data.verificationId} · Timestamp: {data.timestamp}</p>
        </Section>
      </Panel>
    </div>
  );
}
