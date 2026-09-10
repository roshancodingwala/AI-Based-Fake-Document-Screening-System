/**
 * 3.1 — Biometric Preprocessing: Face Detection & Alignment
 *
 * SCOPE: This page covers ONLY sub-module 3.1.
 * It does NOT show face matching, liveness, or identity search
 * (those belong to 3.2 / 3.3 which are other team members' modules).
 *
 * Features:
 *  - Image upload with drag-and-drop
 *  - Animated pipeline steps (Detection → Count → Landmarks → Alignment)
 *  - Original image with real bounding box + landmark overlays (Canvas API)
 *  - Aligned face display (224×224 base64 JPEG from backend)
 *  - Detection metadata cards
 *  - Clear error states for all edge cases
 */

import { useRef, useState, useCallback, useEffect } from "react";
import {
  ScanFace,
  UploadCloud,
  X,
  RefreshCw,
  CheckCircle2,
  Circle,
  Loader2,
  AlertTriangle,
  Users,
  Eye,
  Crosshair,
  RotateCcw,
} from "lucide-react";
import { Panel, PanelHeader, StatCard, StageIcon } from "../components/Common";
import { API_BASE_URL, API_KEY, cn } from "../lib/utils";

// ---------------------------------------------------------------------------
// Types mirroring the backend FaceDetectResponse schema
// ---------------------------------------------------------------------------

interface Landmarks {
  left_eye:    [number, number];
  right_eye:   [number, number];
  nose:        [number, number];
  mouth_left:  [number, number];
  mouth_right: [number, number];
}

interface AlignmentInfo {
  performed:      boolean;
  rotation_angle: number;
  output_width:   number;
  output_height:  number;
}

interface FaceDetectResult {
  success:              boolean;
  status:               string;
  face_detected:        boolean;
  face_count:           number;
  detection_confidence: number | null;
  landmarks_detected:   boolean;
  landmarks:            Landmarks | null;
  bounding_box:         [number, number, number, number] | null;
  alignment:            AlignmentInfo;
  aligned_face_b64:     string | null;
  model:                string;
  message:              string | null;
}

// ---------------------------------------------------------------------------
// Pipeline step definition
// ---------------------------------------------------------------------------

type PipelineStepStatus = "pending" | "processing" | "completed" | "failed";

interface PipelineStep {
  key:   string;
  label: string;
  desc:  string;
}

const PIPELINE_STEPS: PipelineStep[] = [
  { key: "detect",    label: "Face Detection",       desc: "Running MediaPipe FaceLandmarker" },
  { key: "count",     label: "Face Count Validation", desc: "Ensuring exactly one face is present" },
  { key: "landmarks", label: "Landmark Extraction",   desc: "Locating 5 canonical facial points" },
  { key: "align",     label: "Geometric Alignment",   desc: "Normalising rotation via eye centres" },
];

// ---------------------------------------------------------------------------
// Bounding box + landmark canvas overlay
// ---------------------------------------------------------------------------

function FaceOverlayCanvas({
  imgSrc,
  bbox,
  landmarks,
  imgNaturalWidth,
  imgNaturalHeight,
}: {
  imgSrc: string;
  bbox: [number, number, number, number] | null;
  landmarks: Landmarks | null;
  imgNaturalWidth: number;
  imgNaturalHeight: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || imgNaturalWidth === 0) return;

    const displayW = container.clientWidth;
    const displayH = container.clientHeight;
    canvas.width  = displayW;
    canvas.height = displayH;

    const scaleX = displayW / imgNaturalWidth;
    const scaleY = displayH / imgNaturalHeight;

    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, displayW, displayH);

    // Draw bounding box
    if (bbox) {
      const [x1, y1, x2, y2] = bbox;
      const rx1 = x1 * scaleX, ry1 = y1 * scaleY;
      const rw  = (x2 - x1) * scaleX, rh = (y2 - y1) * scaleY;

      ctx.strokeStyle = "rgba(42, 199, 184, 0.9)";
      ctx.lineWidth   = 2;
      ctx.strokeRect(rx1, ry1, rw, rh);

      // Corner markers
      const cs = Math.min(rw, rh) * 0.15;
      ctx.strokeStyle = "rgba(42, 199, 184, 1)";
      ctx.lineWidth   = 3;
      [[rx1, ry1, 1, 1], [rx1 + rw, ry1, -1, 1],
       [rx1, ry1 + rh, 1, -1], [rx1 + rw, ry1 + rh, -1, -1]].forEach(
        ([cx, cy, dx, dy]) => {
          ctx.beginPath();
          ctx.moveTo(cx as number + (dx as number) * cs, cy as number);
          ctx.lineTo(cx as number, cy as number);
          ctx.lineTo(cx as number, cy as number + (dy as number) * cs);
          ctx.stroke();
        }
      );

      // Label
      ctx.fillStyle    = "rgba(42, 199, 184, 0.95)";
      ctx.font         = "bold 11px 'JetBrains Mono', monospace";
      ctx.fillText("FACE DETECTED", rx1 + 4, ry1 - 6);
    }

    // Draw landmark dots
    if (landmarks) {
      const points: [string, [number, number]][] = [
        ["L.Eye",   landmarks.left_eye],
        ["R.Eye",   landmarks.right_eye],
        ["Nose",    landmarks.nose],
        ["M.L",     landmarks.mouth_left],
        ["M.R",     landmarks.mouth_right],
      ];
      points.forEach(([label, [lx, ly]]) => {
        const px = lx * scaleX;
        const py = ly * scaleY;
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(232, 169, 59, 0.95)";
        ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,0.6)";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = "rgba(232, 169, 59, 1)";
        ctx.font = "9px 'JetBrains Mono', monospace";
        ctx.fillText(label, px + 6, py - 4);
      });
    }
  }, [bbox, landmarks, imgNaturalWidth, imgNaturalHeight]);

  useEffect(() => {
    draw();
    const ro = new ResizeObserver(draw);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [draw]);

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <img
        src={imgSrc}
        alt="Original uploaded face"
        className="w-full h-full object-contain rounded"
      />
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full pointer-events-none"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error / status message component
// ---------------------------------------------------------------------------

function StatusMessage({ result }: { result: FaceDetectResult }) {
  if (result.success) return null;

  const iconMap: Record<string, React.ReactNode> = {
    NO_FACE_DETECTED:        <ScanFace size={18} />,
    MULTIPLE_FACES_DETECTED: <Users size={18} />,
    LOW_QUALITY:             <AlertTriangle size={18} />,
    INVALID_IMAGE:           <X size={18} />,
    ALIGNMENT_FAILED:        <RotateCcw size={18} />,
  };

  const colorMap: Record<string, string> = {
    NO_FACE_DETECTED:        "border-warning/40 bg-warning/5 text-warning",
    MULTIPLE_FACES_DETECTED: "border-danger/40 bg-danger/5 text-danger",
    LOW_QUALITY:             "border-warning/40 bg-warning/5 text-warning",
    INVALID_IMAGE:           "border-danger/40 bg-danger/5 text-danger",
    ALIGNMENT_FAILED:        "border-warning/40 bg-warning/5 text-warning",
  };

  const cls = colorMap[result.status] ?? "border-base-border2 bg-base-panel2 text-ink-muted";

  return (
    <div className={cn("flex items-start gap-3 rounded-lg border p-4", cls)}>
      <span className="mt-0.5 shrink-0">{iconMap[result.status]}</span>
      <div>
        <p className="font-semibold text-sm">{result.status.replace(/_/g, " ")}</p>
        {result.message && (
          <p className="mt-0.5 text-xs opacity-80">{result.message}</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function BiometricDetection() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl,   setPreviewUrl]   = useState<string | null>(null);
  const [naturalW,     setNaturalW]     = useState(0);
  const [naturalH,     setNaturalH]     = useState(0);
  const [running,      setRunning]      = useState(false);
  const [stepStatuses, setStepStatuses] = useState<PipelineStepStatus[]>(
    Array(PIPELINE_STEPS.length).fill("pending")
  );
  const [result,       setResult]       = useState<FaceDetectResult | null>(null);
  const [error,        setError]        = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── helpers ──────────────────────────────────────────────────────────────

  const resetState = () => {
    setResult(null);
    setError(null);
    setStepStatuses(Array(PIPELINE_STEPS.length).fill("pending"));
  };

  const handleFile = (file: File) => {
    resetState();
    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    const img = new Image();
    img.onload = () => { setNaturalW(img.naturalWidth); setNaturalH(img.naturalHeight); };
    img.src = url;
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  // ── animate pipeline steps while waiting for API ─────────────────────────

  const animateSteps = (count: number, intervalMs: number): Promise<void> => {
    return new Promise((resolve) => {
      let i = 0;
      const tick = () => {
        setStepStatuses((prev) => {
          const next = [...prev];
          if (i > 0) next[i - 1] = "processing";
          if (i < count) next[i] = "processing";
          return next;
        });
        i++;
        if (i < count) setTimeout(tick, intervalMs);
        else resolve();
      };
      tick();
    });
  };

  const markStepsFromResult = (res: FaceDetectResult) => {
    setStepStatuses((_prev) => {
      const next: PipelineStepStatus[] = ["pending", "pending", "pending", "pending"];
      // step 0: detect
      next[0] = res.face_detected ? "completed" : "failed";
      // step 1: count
      if (res.face_count === 1) next[1] = "completed";
      else if (res.face_count > 1) next[1] = "failed";
      else next[1] = res.face_detected ? "failed" : "pending";
      // step 2: landmarks
      next[2] = res.landmarks_detected ? "completed" : (res.face_count === 1 ? "failed" : "pending");
      // step 3: alignment
      next[3] = res.alignment.performed ? "completed" : (res.landmarks_detected ? "failed" : "pending");
      return next;
    });
  };

  // ── main API call ─────────────────────────────────────────────────────────

  const analyzeImage = async () => {
    if (!selectedFile) { setError("Please select an image first."); return; }
    setRunning(true);
    setError(null);
    setResult(null);
    setStepStatuses(Array(PIPELINE_STEPS.length).fill("pending"));

    // Start step animation concurrently with the API call
    const animPromise = animateSteps(PIPELINE_STEPS.length, 600);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_BASE_URL}/api/face/detect`, {
        method: "POST",
        headers: { "X-API-Key": API_KEY },
        body: formData,
      });

      await animPromise;

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Backend error ${response.status}: ${text}`);
      }

      const data: FaceDetectResult = await response.json();
      markStepsFromResult(data);
      setResult(data);
    } catch (err) {
      await animPromise;
      setStepStatuses(Array(PIPELINE_STEPS.length).fill("failed"));
      setError(
        err instanceof Error
          ? err.message
          : "Could not connect to the backend. Is the server running?"
      );
    } finally {
      setRunning(false);
    }
  };

  // ── render ────────────────────────────────────────────────────────────────

  const confidencePct = result?.detection_confidence != null
    ? `${(result.detection_confidence * 100).toFixed(1)}%`
    : "—";

  return (
    <div className="space-y-6">
      {/* ── Page header ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">
            3.1 — Biometric Preprocessing
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Face Detection &amp; Alignment · Real MediaPipe CV analysis. Upload a single-face image to begin.
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-bg px-3 py-1 text-xs font-semibold text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
          Live AI · MediaPipe
        </span>
      </div>

      {/* ── Top row: upload + pipeline ── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        {/* Upload */}
        <Panel className="xl:col-span-2">
          <PanelHeader title="Upload Image" subtitle="JPEG or PNG, up to 10 MB" />
          <div className="p-4 space-y-4">
            <label
              htmlFor="face-upload"
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition",
                previewUrl
                  ? "border-accent/50 bg-accent-bg/30"
                  : "border-base-border2 bg-base-panel2 hover:border-accent/50"
              )}
            >
              <UploadCloud size={28} className="text-ink-faint" />
              <p className="text-sm font-medium text-ink">
                {selectedFile ? selectedFile.name : "Drag & drop or click to browse"}
              </p>
              <p className="text-xs text-ink-faint">Single face image recommended</p>
              <input
                id="face-upload"
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
              />
            </label>

            {previewUrl && (
              <div className="flex items-center justify-between rounded-md border border-base-border bg-base-panel2 px-3 py-2">
                <span className="font-mono text-xs text-accent truncate max-w-[160px]">
                  {selectedFile?.name}
                </span>
                <button
                  onClick={() => {
                    setSelectedFile(null); setPreviewUrl(null);
                    resetState();
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="ml-2 text-ink-faint hover:text-danger"
                >
                  <X size={14} />
                </button>
              </div>
            )}

            {error && (
              <p className="rounded-md border border-danger/30 bg-danger/5 p-2 text-xs text-danger">
                {error}
              </p>
            )}

            <button
              id="analyze-face-btn"
              onClick={analyzeImage}
              disabled={running || !selectedFile}
              className="w-full rounded-md bg-accent py-2.5 text-sm font-semibold text-base transition hover:bg-accent-dim disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {running ? (
                <><Loader2 size={16} className="animate-spin" /> Analyzing…</>
              ) : (
                <><ScanFace size={16} /> Analyze Face</>
              )}
            </button>
          </div>
        </Panel>

        {/* Pipeline steps */}
        <Panel className="xl:col-span-3">
          <PanelHeader
            title="Processing Pipeline"
            subtitle="3.1 — real-time detection & alignment stages"
          />
          <div className="p-5">
            {stepStatuses.every((s) => s === "pending") && !running ? (
              <div className="flex h-40 flex-col items-center justify-center gap-2 text-ink-faint">
                <Circle size={32} className="opacity-30" />
                <p className="text-sm">Upload an image and click "Analyze Face" to begin.</p>
              </div>
            ) : (
              <ol className="space-y-0">
                {PIPELINE_STEPS.map((step, idx) => (
                  <li key={step.key} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <StageIcon status={stepStatuses[idx]} />
                      {idx < PIPELINE_STEPS.length - 1 && (
                        <div
                          className={cn(
                            "w-0.5 flex-1",
                            stepStatuses[idx] === "completed"
                              ? "bg-accent/40"
                              : "bg-base-border2"
                          )}
                          style={{ minHeight: 28 }}
                        />
                      )}
                    </div>
                    <div className="pb-6">
                      <p className="text-sm font-medium text-ink">{step.label}</p>
                      <p className="mt-0.5 text-xs text-ink-muted">
                        {stepStatuses[idx] === "processing" && (
                          <span className="text-info">{step.desc}…</span>
                        )}
                        {stepStatuses[idx] === "completed" && "Completed ✓"}
                        {stepStatuses[idx] === "failed"    && "Step failed or skipped"}
                        {stepStatuses[idx] === "pending"   && "Waiting…"}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Panel>
      </div>

      {/* ── Results section (only shown after API responds) ── */}
      {result && (
        <>
          {/* Error / status message */}
          {!result.success && <StatusMessage result={result} />}

          {/* Metadata stat cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Face Detected"
              value={result.face_detected ? "Yes" : "No"}
              icon={<ScanFace size={16} />}
              tone={result.face_detected ? "success" : "danger"}
            />
            <StatCard
              label="Face Count"
              value={result.face_count}
              icon={<Users size={16} />}
              tone={result.face_count === 1 ? "success" : result.face_count > 1 ? "danger" : "default"}
            />
            <StatCard
              label="Confidence"
              value={confidencePct}
              icon={<Eye size={16} />}
              tone={
                result.detection_confidence == null ? "default"
                  : result.detection_confidence >= 0.75 ? "success"
                  : result.detection_confidence >= 0.55 ? "warning"
                  : "danger"
              }
            />
            <StatCard
              label="Alignment"
              value={result.alignment.performed ? `${result.alignment.rotation_angle}°` : "—"}
              hint={result.alignment.performed ? `${result.alignment.output_width}×${result.alignment.output_height}` : undefined}
              icon={<RotateCcw size={16} />}
              tone={result.alignment.performed ? "accent" : "default"}
            />
          </div>

          {/* Image panels — original with overlay + aligned face */}
          {(previewUrl || result.aligned_face_b64) && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Original image with bbox + landmark overlay */}
              {previewUrl && (
                <Panel>
                  <PanelHeader
                    title="Original Image"
                    subtitle={
                      result.bounding_box
                        ? "Bounding box & landmarks overlaid from real detection"
                        : "No face detected — no overlay"
                    }
                    right={
                      result.bounding_box && (
                        <span className="flex items-center gap-1 rounded-full border border-accent/30 bg-accent-bg px-2 py-0.5 text-[10px] font-mono text-accent">
                          <Crosshair size={10} /> LIVE BBOX
                        </span>
                      )
                    }
                  />
                  <div className="p-4">
                    <div className="h-64 overflow-hidden rounded-md border border-base-border bg-base-panel2">
                      <FaceOverlayCanvas
                        imgSrc={previewUrl}
                        bbox={result.bounding_box}
                        landmarks={result.landmarks}
                        imgNaturalWidth={naturalW}
                        imgNaturalHeight={naturalH}
                      />
                    </div>
                    {result.bounding_box && (
                      <p className="mt-2 font-mono text-[10px] text-ink-faint">
                        bbox [{result.bounding_box.join(", ")}] px
                      </p>
                    )}
                  </div>
                </Panel>
              )}

              {/* Aligned face output */}
              {result.aligned_face_b64 ? (
                <Panel>
                  <PanelHeader
                    title="Aligned Face"
                    subtitle={`${result.alignment.output_width}×${result.alignment.output_height} · geometrically normalised`}
                    right={
                      <span className="flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success">
                        <CheckCircle2 size={10} /> ALIGNED
                      </span>
                    }
                  />
                  <div className="p-4">
                    <div className="flex h-64 items-center justify-center overflow-hidden rounded-md border border-base-border bg-base-panel2">
                      <img
                        src={`data:image/jpeg;base64,${result.aligned_face_b64}`}
                        alt="Aligned and normalised face"
                        className="h-full w-auto object-contain"
                        style={{ imageRendering: "auto" }}
                      />
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3">
                      <p className="font-mono text-[10px] text-ink-faint">
                        rotation corrected: {result.alignment.rotation_angle}°
                      </p>
                      {result.landmarks && (
                        <p className="font-mono text-[10px] text-ink-faint">
                          landmarks: 5-point ✓
                        </p>
                      )}
                    </div>
                  </div>
                </Panel>
              ) : (
                /* No aligned face — show placeholder with reason */
                <Panel>
                  <PanelHeader title="Aligned Face" subtitle="Not available" />
                  <div className="flex h-64 flex-col items-center justify-center gap-3 p-4 text-ink-faint">
                    <ScanFace size={36} className="opacity-30" />
                    <p className="text-sm text-center">
                      {result.message ?? "Alignment could not be performed."}
                    </p>
                  </div>
                </Panel>
              )}
            </div>
          )}

          {/* Landmark detail table */}
          {result.landmarks && (
            <Panel>
              <PanelHeader
                title="Detected Landmarks"
                subtitle="5-point canonical set — absolute pixel coordinates in original image"
              />
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-base-border text-left text-ink-faint">
                      <th className="px-5 py-3 font-semibold">Point</th>
                      <th className="px-5 py-3 font-semibold text-right">X (px)</th>
                      <th className="px-5 py-3 font-semibold text-right">Y (px)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {([
                      ["Left Eye",    result.landmarks.left_eye],
                      ["Right Eye",   result.landmarks.right_eye],
                      ["Nose",        result.landmarks.nose],
                      ["Mouth Left",  result.landmarks.mouth_left],
                      ["Mouth Right", result.landmarks.mouth_right],
                    ] as [string, [number, number]][]).map(([label, [x, y]]) => (
                      <tr key={label} className="border-b border-base-border last:border-0 hover:bg-base-panel2">
                        <td className="px-5 py-3 font-medium text-ink">{label}</td>
                        <td className="px-5 py-3 text-right font-mono text-ink-muted">{x.toFixed(1)}</td>
                        <td className="px-5 py-3 text-right font-mono text-ink-muted">{y.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {/* Reset button */}
          <div className="flex justify-center">
            <button
              onClick={() => {
                setSelectedFile(null); setPreviewUrl(null); resetState();
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              className="flex items-center gap-2 rounded-md border border-base-border2 bg-base-panel px-4 py-2 text-sm text-ink-muted hover:border-accent hover:text-ink"
            >
              <RefreshCw size={14} /> Analyze Another Image
            </button>
          </div>
        </>
      )}
    </div>
  );
}
