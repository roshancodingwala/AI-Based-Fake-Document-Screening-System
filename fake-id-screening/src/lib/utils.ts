import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function riskColors(level: "low" | "medium" | "high" | "critical") {
  switch (level) {
    case "low":
      return { text: "text-success", bg: "bg-success/10", border: "border-success/30", dot: "bg-success" };
    case "medium":
      return { text: "text-warning", bg: "bg-warning/10", border: "border-warning/30", dot: "bg-warning" };
    case "high":
      return { text: "text-danger", bg: "bg-danger/10", border: "border-danger/30", dot: "bg-danger" };
    case "critical":
      return { text: "text-[#C084FC]", bg: "bg-[#C084FC]/10", border: "border-[#C084FC]/30", dot: "bg-[#C084FC]" };
  }
}

export function severityColors(severity: "low" | "medium" | "high" | "critical") {
  return riskColors(severity);
}

export function statusColors(status: string) {
  switch (status) {
    case "Verified":
    case "Confirmed":
    case "VERIFIED":
      return { text: "text-success", bg: "bg-success/10", border: "border-success/30" };
    case "Suspicious":
      return { text: "text-warning", bg: "bg-warning/10", border: "border-warning/30" };
    case "High Risk":
    case "FLAGGED":
      return { text: "text-danger", bg: "bg-danger/10", border: "border-danger/30" };
    case "Blacklisted":
      return { text: "text-[#C084FC]", bg: "bg-[#C084FC]/10", border: "border-[#C084FC]/30" };
    default:
      return { text: "text-ink-muted", bg: "bg-base-panel2", border: "border-base-border" };
  }
}

export const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const API_KEY = (import.meta as any).env?.VITE_API_KEY || "demo-officer-key-12345";

export async function apiRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : "/" + endpoint}`;
  const headers = new Headers(options.headers || {});
  if (!headers.has("X-API-Key")) {
    headers.set("X-API-Key", API_KEY);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`API Error ${response.status}: ${errText || response.statusText}`);
  }

  return response.json();
}
