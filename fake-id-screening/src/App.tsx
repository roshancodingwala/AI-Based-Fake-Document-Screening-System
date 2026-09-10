import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import { Loader2 } from "lucide-react";
import { ThemeProvider } from "./lib/ThemeContext";

// Lazy-loaded pages for optimal route-level code splitting
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Screening = lazy(() => import("./pages/Screening"));
const Results = lazy(() => import("./pages/Results"));
const Identity = lazy(() => import("./pages/Identity"));
const FraudNetwork = lazy(() => import("./pages/FraudNetwork"));
const DocumentDNA = lazy(() => import("./pages/DocumentDNA"));
const DocumentHistory = lazy(() => import("./pages/DocumentHistory"));
const Checkpoints = lazy(() => import("./pages/Checkpoints"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Blockchain = lazy(() => import("./pages/Blockchain"));
const SelfTest = lazy(() => import("./pages/SelfTest"));
const Reports = lazy(() => import("./pages/Reports"));
const Settings = lazy(() => import("./pages/Settings"));

function LoadingFallback() {
  return (
    <div className="flex h-64 w-full items-center justify-center text-ink-muted">
      <div className="flex flex-col items-center gap-2">
        <Loader2 className="animate-spin text-accent" size={28} />
        <span className="text-xs">Loading module...</span>
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Login />} />
            <Route path="/dashboard" element={<Shell><Dashboard /></Shell>} />
            <Route path="/screening" element={<Shell><Screening /></Shell>} />
            <Route path="/results" element={<Shell><Results /></Shell>} />
            <Route path="/identity" element={<Shell><Identity /></Shell>} />
            <Route path="/fraud-network" element={<Shell><FraudNetwork /></Shell>} />
            <Route path="/document-dna" element={<Shell><DocumentDNA /></Shell>} />
            <Route path="/history" element={<Shell><DocumentHistory /></Shell>} />
            <Route path="/checkpoints" element={<Shell><Checkpoints /></Shell>} />
            <Route path="/alerts" element={<Shell><Alerts /></Shell>} />
            <Route path="/blockchain" element={<Shell><Blockchain /></Shell>} />
            <Route path="/self-test" element={<Shell><SelfTest /></Shell>} />
            <Route path="/reports" element={<Shell><Reports /></Shell>} />
            <Route path="/settings" element={<Shell><Settings /></Shell>} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ThemeProvider>
  );
}
