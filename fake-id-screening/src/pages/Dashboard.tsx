import { FileCheck2, ShieldCheck, TriangleAlert, ShieldX, Users2, Ban } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { Panel, PanelHeader, StatCard, StatusPill } from "../components/Common";
import { kpis, weeklyVolume, riskDistribution, recentActivity } from "../data/mockData";
import { Link } from "react-router-dom";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-ink">Command Overview</h1>
        <p className="mt-1 text-sm text-ink-muted">Live screening summary across all checkpoints — last 24 hours.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total Checked" value={kpis.totalChecked.toLocaleString()} icon={<FileCheck2 size={16} />} hint="Today" />
        <StatCard label="Verified" value={kpis.verified.toLocaleString()} icon={<ShieldCheck size={16} />} tone="success" hint="91.1% pass rate" />
        <StatCard label="Suspicious" value={kpis.suspicious.toLocaleString()} icon={<TriangleAlert size={16} />} tone="warning" hint="Needs review" />
        <StatCard label="High Risk" value={kpis.highRisk} icon={<ShieldX size={16} />} tone="danger" hint="Escalated" />
        <StatCard label="Multi-Identity Alerts" value={kpis.multipleIdentity} icon={<Users2 size={16} />} tone="danger" hint="Active investigations" />
        <StatCard label="Blacklisted" value={kpis.blacklisted} icon={<Ban size={16} />} tone="danger" hint="Confirmed matches" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHeader title="Verification Volume — 7 Day Trend" subtitle="Total documents checked vs. flagged for review" />
          <div className="h-64 px-4 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weeklyVolume}>
                <CartesianGrid strokeDasharray="3 3" stroke="#233150" vertical={false} />
                <XAxis dataKey="day" stroke="#5D6C8A" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#5D6C8A" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ background: "#111A2E", border: "1px solid #233150", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#E7ECF5" }}
                />
                <Bar dataKey="checked" fill="#2AC7B8" radius={[4, 4, 0, 0]} name="Checked" />
                <Bar dataKey="flagged" fill="#F0495A" radius={[4, 4, 0, 0]} name="Flagged" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Risk Distribution" subtitle="All documents screened today" />
          <div className="h-64 px-4 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={riskDistribution} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={3}>
                  {riskDistribution.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} stroke="none" />
                  ))}
                </Pie>
                <Legend verticalAlign="bottom" height={24} iconType="circle" wrapperStyle={{ fontSize: 12, color: "#8C9AB5" }} />
                <Tooltip contentStyle={{ background: "#111A2E", border: "1px solid #233150", borderRadius: 8, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Recent Verification Activity"
          subtitle="Most recent document checks across all checkpoints"
          right={
            <Link to="/alerts" className="text-xs font-medium text-accent hover:underline">
              View all alerts →
            </Link>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-base-border text-xs uppercase tracking-wide text-ink-faint">
                <th className="px-5 py-3 font-medium">Case ID</th>
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Document</th>
                <th className="px-5 py-3 font-medium">Checkpoint</th>
                <th className="px-5 py-3 font-medium">Risk Score</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody>
              {recentActivity.map((r) => (
                <tr key={r.id} className="border-b border-base-border/60 last:border-0 hover:bg-base-panel2/60">
                  <td className="px-5 py-3 font-mono text-xs text-ink-muted">
                    <Link to="/results" className="hover:text-accent">{r.id}</Link>
                  </td>
                  <td className="px-5 py-3 font-medium text-ink">{r.name}</td>
                  <td className="px-5 py-3 text-ink-muted">{r.docType} · {r.docNumber}</td>
                  <td className="px-5 py-3 text-ink-muted">{r.checkpoint}</td>
                  <td className="px-5 py-3">
                    <span className="font-mono font-semibold text-ink">{r.riskScore}</span>
                    <span className="text-ink-faint">/100</span>
                  </td>
                  <td className="px-5 py-3"><StatusPill status={r.status} /></td>
                  <td className="px-5 py-3 text-xs text-ink-faint">{r.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
