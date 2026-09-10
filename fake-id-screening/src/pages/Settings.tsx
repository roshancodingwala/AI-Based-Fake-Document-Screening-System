import { useState } from "react";
import { Panel, PanelHeader, DemoTag } from "../components/Common";
import { officer } from "../data/mockData";

function Toggle({ label, description, defaultOn = false }: { label: string; description: string; defaultOn?: boolean }) {
  const [on, setOn] = useState(defaultOn);
  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="text-xs text-ink-muted">{description}</p>
      </div>
      <button
        onClick={() => setOn((o) => !o)}
        className={`h-6 w-11 shrink-0 rounded-full transition ${on ? "bg-accent" : "bg-base-border2"}`}
      >
        <span className={`block h-5 w-5 translate-y-0.5 rounded-full bg-white transition ${on ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}

export default function Settings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">Settings</h1>
          <p className="mt-1 text-sm text-ink-muted">Manage your officer profile, security and system preferences.</p>
        </div>
        <DemoTag />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel>
          <PanelHeader title="Officer Profile" />
          <div className="space-y-4 p-5">
            <div className="flex items-center gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/20 text-lg font-bold text-accent">
                PN
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">{officer.name}</p>
                <p className="text-xs text-ink-muted">{officer.rank}</p>
                <p className="text-xs text-ink-faint">{officer.post}</p>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Officer ID</label>
              <input disabled value={officer.id} className="w-full rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-sm text-ink-muted" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">Email</label>
              <input disabled value={officer.email} className="w-full rounded-md border border-base-border2 bg-base-panel2 px-3 py-2 text-sm text-ink-muted" />
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Security Settings" />
          <div className="divide-y divide-base-border/60 px-5">
            <Toggle label="Two-factor authentication" description="Require an OTP in addition to password on login" defaultOn />
            <Toggle label="Biometric sign-in" description="Allow fingerprint/face sign-in on this workstation" defaultOn />
            <Toggle label="Auto-lock after inactivity" description="Lock session after 5 minutes of inactivity" defaultOn />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Notification Settings" />
          <div className="divide-y divide-base-border/60 px-5">
            <Toggle label="Critical alerts" description="Multiple identity, blacklist and cross-checkpoint alerts" defaultOn />
            <Toggle label="Daily summary email" description="Send a daily screening summary to your inbox" />
            <Toggle label="Desktop notifications" description="Show a popup for high-risk verifications" defaultOn />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="System Settings" />
          <div className="divide-y divide-base-border/60 px-5">
            <Toggle label="Auto-escalate risk ≥ 85" description="Automatically flag cases above this score for supervisor review" defaultOn />
            <Toggle label="Show DEMO/SIMULATED tags" description="Display simulation labels on AI-generated results" defaultOn />
            <Toggle label="Dark theme" description="Use the dark security theme across the platform" defaultOn />
          </div>
        </Panel>
      </div>
    </div>
  );
}
