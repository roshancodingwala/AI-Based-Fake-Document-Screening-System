import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BookUser,
  Stamp,
  IdCard,
  Car,
  FileBadge2,
  Camera,
  UploadCloud,
} from "lucide-react";
import { Panel, PanelHeader, StageIcon, DemoTag } from "../components/Common";
import { verificationPipelineStages } from "../data/mockData";
import type { StageStatus } from "../data/mockData";
import { API_BASE_URL, API_KEY } from "../lib/utils";

const docOptions = [
  { key: "passport", label: "Passport", icon: BookUser },
  { key: "visa", label: "Visa", icon: Stamp },
  { key: "national-id", label: "National ID", icon: IdCard },
  { key: "driving-licence", label: "Driving Licence", icon: Car },
  { key: "permit", label: "Permit", icon: FileBadge2 },
];

export default function Screening() {
  const navigate = useNavigate();

  const [selectedDoc, setSelectedDoc] = useState("passport");
  const [running, setRunning] = useState(false);
  const [activeStage, setActiveStage] = useState(-1);
  const [fileName, setFileName] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setFileName(file.name);
    setError(null);
  };

  const startPipeline = async () => {
    if (!selectedFile) {
      setError("Please select a document first.");
      return;
    }

    setRunning(true);
    setError(null);
    setActiveStage(0);

    try {
      const formData = new FormData();

      formData.append("document_image", selectedFile);
      formData.append(
        "document_type",
        selectedDoc === "passport"
          ? "Passport"
          : selectedDoc
      );
      formData.append(
        "checkpoint_name",
        "Terminal 3 - Counter 4"
      );
      formData.append("officer_id", "OFFICER-DEMO-001");

      const response = await fetch(`${API_BASE_URL}/api/screen`, {
        method: "POST",
        headers: {
          "X-API-Key": API_KEY,
        },
        body: formData,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(
          `Backend error ${response.status}: ${text}`
        );
      }

      const result = await response.json();

      console.log("BACKEND SCREENING RESULT:", result);

      // Animate stages for UI while backend result is being shown.
      verificationPipelineStages.forEach((_, idx) => {
        setTimeout(() => {
          setActiveStage(idx);
        }, idx * 500);
      });

      setTimeout(() => {
        setRunning(false);

        // Save backend result for Results page.
        localStorage.setItem(
          "sentry_screening_result",
          JSON.stringify(result)
        );
      }, verificationPipelineStages.length * 500);

    } catch (err) {
      console.error(err);

      setRunning(false);
      setActiveStage(-1);

      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to backend."
      );
    }
  };

  const stageStatus = (idx: number): StageStatus => {
    if (activeStage < 0) return "pending";

    if (idx < activeStage) return "completed";

    if (idx === activeStage) {
      return running ? "processing" : "completed";
    }

    return "pending";
  };

  const pipelineDone =
    activeStage === verificationPipelineStages.length - 1 &&
    !running;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">
            Document Screening
          </h1>

          <p className="mt-1 text-sm text-ink-muted">
            Upload or scan a document to begin AI-assisted verification.
          </p>
        </div>

        <DemoTag />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">

        <Panel className="xl:col-span-2">
          <PanelHeader title="Select Document Type" />

          <div className="grid grid-cols-2 gap-2 p-4">
            {docOptions.map((opt) => (
              <button
                key={opt.key}
                onClick={() => setSelectedDoc(opt.key)}
                className={`flex flex-col items-center gap-2 rounded-md border px-3 py-4 text-xs font-medium transition ${
                  selectedDoc === opt.key
                    ? "border-accent bg-accent-bg text-accent"
                    : "border-base-border2 bg-base-panel2 text-ink-muted hover:border-accent/50 hover:text-ink"
                }`}
              >
                <opt.icon size={20} />
                {opt.label}
              </button>
            ))}

            <button className="flex flex-col items-center gap-2 rounded-md border border-dashed border-base-border2 bg-base-panel2 px-3 py-4 text-xs font-medium text-ink-muted hover:border-accent/50 hover:text-ink">
              <Camera size={20} />
              Camera / Scan
            </button>
          </div>

          <div className="border-t border-base-border p-4">

            <label
              htmlFor="document-upload"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-base-border2 bg-base-panel2 px-4 py-10 text-center"
            >
              <UploadCloud
                size={28}
                className="text-ink-faint"
              />

              <p className="text-sm font-medium text-ink">
                Drag and drop the document image here
              </p>

              <p className="text-xs text-ink-faint">
                or click to browse · JPG, PNG, PDF up to 10MB
              </p>

              <span className="mt-2 rounded-md border border-base-border2 px-3 py-1.5 text-xs font-medium text-ink-muted hover:border-accent hover:text-accent">
                Browse files
              </span>

              <input
                id="document-upload"
                type="file"
                accept=".jpg,.jpeg,.png,.pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];

                  if (file) {
                    handleFileSelect(file);
                  }
                }}
              />

              {fileName && (
                <p className="mt-2 font-mono text-[11px] text-accent">
                  {fileName} selected
                </p>
              )}
            </label>

            {error && (
              <p className="mt-3 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
                {error}
              </p>
            )}

            <button
              onClick={startPipeline}
              disabled={running}
              className="mt-4 w-full rounded-md bg-accent py-2.5 text-sm font-semibold text-base transition hover:bg-accent-dim disabled:opacity-50"
            >
              {running
                ? "Running Verification..."
                : "Start Verification"}
            </button>
          </div>
        </Panel>

        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Verification Pipeline"
            subtitle="Real-time processing stages for this document"
          />

          <div className="p-5">

            {activeStage < 0 ? (
              <div className="flex h-64 flex-col items-center justify-center gap-2 text-center text-ink-faint">
                <p className="text-sm">
                  No document is currently processing.
                </p>

                <p className="text-xs">
                  Upload a document and start verification to see live pipeline status.
                </p>
              </div>
            ) : (
              <ol className="space-y-0">
                {verificationPipelineStages.map((stage, idx) => {
                  const status = stageStatus(idx);

                  return (
                    <li
                      key={stage.key}
                      className="flex gap-4"
                    >
                      <div className="flex flex-col items-center">
                        <StageIcon status={status} />

                        {idx !== verificationPipelineStages.length - 1 && (
                          <div
                            className={`w-0.5 flex-1 ${
                              idx < activeStage
                                ? "bg-accent/40"
                                : "bg-base-border2"
                            }`}
                            style={{ minHeight: 28 }}
                          />
                        )}
                      </div>

                      <div className="pb-6">
                        <p className="text-sm font-medium text-ink">
                          {stage.label}
                        </p>

                        <p className="mt-0.5 text-xs text-ink-muted">
                          {status === "completed" &&
                            "Passed automated checks."}

                          {status === "processing" &&
                            "Analyzing..."}

                          {status === "warning" &&
                            "Anomaly detected — flagged for officer review."}

                          {status === "failed" &&
                            "Check failed."}

                          {status === "pending" &&
                            "Waiting in queue."}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}

            {pipelineDone && (
              <button
                onClick={() => navigate("/results")}
                className="w-full rounded-md border border-accent bg-accent-bg py-2.5 text-sm font-semibold text-accent hover:bg-accent/20"
              >
                View Full Verification Result →
              </button>
            )}

          </div>
        </Panel>

      </div>
    </div>
  );
}