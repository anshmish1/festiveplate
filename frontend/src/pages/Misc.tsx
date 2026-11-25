import { FormEvent, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/Layout";
import { Bar, Button, Card, DemoBadge, ErrorBox, Field, inputCls, Loading, Notice, SimulatedBanner, Stat } from "../components/ui";
import type { Impact, Incident, Notification } from "../types";
import { CATEGORY_LABEL, errText, fmtDateTime, useLoad } from "../utils";

// ---------------- Impact dashboard ----------------

export function ImpactDashboard() {
  const q = useLoad(() => api.get<Impact>("/api/impact"), [], 30000);
  if (q.loading) return <Loading />;
  if (q.error || !q.data) return <ErrorBox message={q.error ?? ""} onRetry={() => q.reload()} />;
  const d = q.data;
  if (d.enabled === false) return <Notice>The impact dashboard is currently turned off by the administrator.</Notice>;
  const maxDay = Math.max(1, ...d.delivered_by_day.map((x) => x.portions));
  const maxCat = Math.max(1, ...d.delivered_by_category.map((x) => x.portions));
  return (
    <>
      <PageTitle title="Impact" subtitle={<span className="flex items-center gap-2">Platform-wide food rescue outcomes {d.includes_demo_data && <DemoBadge label="includes demo data" />}</span>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Portions delivered" value={d.delivered_portions} hint={d.definitions.delivered_portions} />
        <Stat label="Portions collected" value={d.collected_portions} hint={d.definitions.collected_portions} />
        <Stat label="Portions reported" value={d.reported_portions} hint={d.definitions.reported_portions} />
        <Stat label="Completed donations" value={d.completed_donations} />
        <Stat label="Avg. time to NGO acceptance" value={d.average_matching_minutes != null ? `${d.average_matching_minutes} min` : "-"} hint={d.definitions.average_matching_minutes} />
        <Stat label="Collection success rate" value={d.collection_success_rate != null ? `${Math.round(d.collection_success_rate * 100)}%` : "-"} hint={d.definitions.collection_success_rate} />
        <Stat label="Verified NGOs" value={d.verified_ngos} />
        <Stat label="Predicted surplus (estimate)" value={d.predicted_surplus_portions} hint={d.definitions.predicted_surplus_portions} />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Card title="Delivered portions by day (IST)">
          {d.delivered_by_day.length === 0 ? <p className="text-sm text-slate-500">No confirmed deliveries yet.</p> : <div className="space-y-2">{d.delivered_by_day.map((x) => <Bar key={x.date} label={x.date} value={x.portions} max={maxDay} />)}</div>}
        </Card>
        <Card title="Delivered portions by food category">
          {d.delivered_by_category.length === 0 ? <p className="text-sm text-slate-500">No confirmed deliveries yet.</p> : <div className="space-y-2">{d.delivered_by_category.map((x) => <Bar key={x.category} label={CATEGORY_LABEL[x.category] ?? x.category} value={x.portions} max={maxCat} />)}</div>}
        </Card>
      </div>
      <p className="mt-4 text-xs text-slate-500">Reported portions are donor estimates. Only volunteer-confirmed deliveries count as rescued food. Predictions are shown separately and never added to rescue totals.</p>
    </>
  );
}

// ---------------- System health ----------------

interface RouteStat { requests: number; errors_5xx: number; errors_4xx: number; avg_latency_ms: number }
interface Health {
  backend: { uptime_seconds: number; total_requests: number; errors_5xx: number; errors_4xx: number; error_rate: number; routes: Record<string, RouteStat>;
    recent_errors: { ts?: string; route?: string; status?: number; error?: string }[]; integration_calls: Record<string, Record<string, number>>; database_ok: boolean; environment: string };
  integrations: {
    sarvam: { configured: boolean; mode: string };
    flagsmith: { configured: boolean; connected: boolean; message: string };
    nudgebee: { state: string; live: boolean; message: string; exposed_signals: string[] };
  };
  notifications: { failed_total: number; recent_failures: Notification[] };
  incident_summary: { generated_by: string; summary: string; open_incidents: number; failed_notifications: number };
  simulated_ai_insights: { simulated: boolean; title: string; insight: string; recommendation: string }[];
}

function Pill({ ok, label }: { ok: boolean | null; label: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${ok === null ? "bg-slate-100 text-slate-600" : ok ? "bg-leaf-100 text-leaf-800" : "bg-turmeric-100 text-turmeric-700"}`}>{label}</span>;
}

export function SystemHealth() {
  const h = useLoad(() => api.get<Health>("/api/admin/system/health"), [], 15000);
  const inc = useLoad(() => api.get<Incident[]>("/api/admin/incidents"), [], 15000);
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      h.reload(true);
      inc.reload(true);
    } catch (e) {
      setErr(errText(e));
    }
  };
  if (h.loading && !h.data) return <Loading />;
  if (h.error || !h.data) return <ErrorBox message={h.error ?? ""} onRetry={() => h.reload()} />;
  const d = h.data;
  const routes = Object.entries(d.backend.routes).sort((a, b) => b[1].requests - a[1].requests);
  return (
    <>
      <PageTitle title="System health" subtitle={`Environment: ${d.backend.environment} · refreshes every 15 s`} />
      {err && <ErrorBox message={err} />}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Database" value={d.backend.database_ok ? "OK" : "DOWN"} />
        <Stat label="Uptime" value={`${Math.floor(d.backend.uptime_seconds / 60)} min`} hint="This API process" />
        <Stat label="Requests" value={d.backend.total_requests} />
        <Stat label="Server errors (5xx)" value={d.backend.errors_5xx} hint={`${(d.backend.error_rate * 100).toFixed(2)}% error rate`} />
        <Stat label="Failed notifications" value={d.notifications.failed_total} />
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <Card title="Sarvam AI">
          <Pill ok={d.integrations.sarvam.configured} label={d.integrations.sarvam.configured ? "Configured" : "Demo mode"} />
          <p className="mt-2 text-sm text-slate-600">{d.integrations.sarvam.mode}</p>
          {Object.entries(d.backend.integration_calls).length > 0 && (
            <ul className="mt-2 text-xs text-slate-600">{Object.entries(d.backend.integration_calls).map(([k, v]) => <li key={k}><code>{k}</code>: {Object.entries(v).map(([s, n]) => `${s} ${n}`).join(", ")}</li>)}</ul>
          )}
        </Card>
        <Card title="Flagsmith">
          <Pill ok={d.integrations.flagsmith.connected} label={d.integrations.flagsmith.connected ? "Connected" : d.integrations.flagsmith.configured ? "Unreachable" : "Not configured"} />
          <p className="mt-2 text-sm text-slate-600">{d.integrations.flagsmith.message}</p>
        </Card>
        <Card title="NudgeBee">
          <Pill ok={d.integrations.nudgebee.state === "NOT_CONFIGURED" ? null : false} label={d.integrations.nudgebee.state.replace("_", " ")} />
          <p className="mt-2 text-sm text-slate-600">{d.integrations.nudgebee.message}</p>
          <p className="mt-2 text-xs text-slate-500">Signals exposed for observability tools: {d.integrations.nudgebee.exposed_signals.join(", ")}</p>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Incident summary">
          <p className="text-sm">{d.incident_summary.summary}</p>
          <p className="mt-1 text-xs text-slate-500">Generated by: {d.incident_summary.generated_by}</p>
          <h3 className="mt-4 font-semibold">Incidents</h3>
          {(inc.data ?? []).length === 0 ? <p className="text-sm text-slate-500">No incidents recorded.</p> : (
            <ul className="mt-2 space-y-2 text-sm">
              {inc.data!.map((i) => (
                <li key={i.id} className="rounded-lg border border-cream-300 p-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{i.title}</span>
                    <span className="text-xs">{i.severity} · {i.status} · ×{i.occurrences}</span>
                  </div>
                  <div className="text-xs text-slate-500">{i.category} · last seen {fmtDateTime(i.last_seen)}</div>
                  {i.status === "OPEN" && <Button variant="ghost" className="mt-1 px-0 py-0" onClick={() => act(() => api.post(`/api/admin/incidents/${i.id}/resolve`))}>Mark resolved</Button>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Failed notifications">
          {d.notifications.recent_failures.length === 0 ? <p className="text-sm text-slate-500">No failed notifications.</p> : (
            <ul className="space-y-2 text-sm">
              {d.notifications.recent_failures.map((n) => (
                <li key={n.id} className="rounded-lg border border-cream-300 p-2">
                  <div className="font-medium">{n.title}</div>
                  <div className="text-xs text-chili-700">{n.error}</div>
                  <div className="text-xs text-slate-500">{fmtDateTime(n.created_at)} · language {n.language}</div>
                  <Button variant="ghost" className="mt-1 px-0 py-0" onClick={() => act(() => api.post(`/api/admin/notifications/${n.id}/retry`))}>Retry translation</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="API routes (this process)" className="mt-6">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="p-1">Route</th><th className="p-1">Requests</th><th className="p-1">4xx</th><th className="p-1">5xx</th><th className="p-1">Avg ms</th></tr></thead>
            <tbody>{routes.map(([k, v]) => <tr key={k} className="border-t border-cream-200"><td className="p-1 font-mono text-xs">{k}</td><td className="p-1">{v.requests}</td><td className="p-1">{v.errors_4xx}</td><td className={`p-1 ${v.errors_5xx ? "font-bold text-chili-700" : ""}`}>{v.errors_5xx}</td><td className="p-1">{v.avg_latency_ms}</td></tr>)}</tbody>
          </table>
        </div>
        {d.backend.recent_errors.length > 0 && (
          <>
            <h3 className="mt-4 font-semibold">Recent server errors</h3>
            <ul className="mt-1 text-xs">{d.backend.recent_errors.map((e, i) => <li key={i} className="font-mono">{JSON.stringify(e)}</li>)}</ul>
          </>
        )}
      </Card>

      {d.simulated_ai_insights.length > 0 && (
        <Card title="AI operations insights" className="mt-6">
          <SimulatedBanner>NudgeBee is not connected. The cards below are illustrative examples of AI SRE insights - they are not generated from live telemetry.</SimulatedBanner>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {d.simulated_ai_insights.map((s) => (
              <div key={s.title} className="rounded-lg border-2 border-dashed border-turmeric-500 p-3 text-sm">
                <div className="font-semibold">{s.title}</div>
                <p className="mt-1 text-slate-600">{s.insight}</p>
                <p className="mt-1 text-slate-700"><strong>Suggested:</strong> {s.recommendation}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}

// ---------------- Settings ----------------

export function Settings() {
  const { me, refresh } = useAuth();
  const u = me!.user;
  const [f, setF] = useState({ full_name: u.full_name, phone: u.phone ?? "", preferred_language: u.preferred_language, notify_in_app: u.notify_in_app, notify_sms: u.notify_sms });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ngo = me!.ngo_profile;
  const [ng, setNg] = useState(ngo ? { service_radius_km: String(ngo.service_radius_km), daily_capacity_portions: String(ngo.daily_capacity_portions), accepts_veg: ngo.accepts_veg, accepts_non_veg: ngo.accepts_non_veg, pickup_start_hour: String(ngo.pickup_start_hour), pickup_end_hour: String(ngo.pickup_end_hour), has_vehicle: ngo.has_vehicle } : null);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await api.patch("/api/me/settings", { ...f, phone: f.phone || null });
      if (ng) {
        await api.patch("/api/ngo/profile", {
          service_radius_km: Number(ng.service_radius_km), daily_capacity_portions: Number(ng.daily_capacity_portions), accepts_veg: ng.accepts_veg,
          accepts_non_veg: ng.accepts_non_veg, pickup_start_hour: Number(ng.pickup_start_hour), pickup_end_hour: Number(ng.pickup_end_hour), has_vehicle: ng.has_vehicle,
        });
      }
      await refresh();
      setMsg("Settings saved.");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageTitle title="Settings" subtitle={`${u.email} · ${u.role.toLowerCase()}`} />
      <form onSubmit={save} className="space-y-4">
        <Card title="Profile and notifications">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Full name" htmlFor="s-name"><input id="s-name" className={inputCls} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
            <Field label="Phone" htmlFor="s-phone"><input id="s-phone" type="tel" className={inputCls} value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
            <Field label="Notification language" htmlFor="s-lang" hint="Notifications are translated with Sarvam AI when configured; otherwise sent in English.">
              <select id="s-lang" className={inputCls} value={f.preferred_language} onChange={(e) => setF({ ...f, preferred_language: e.target.value as typeof f.preferred_language })}>
                <option value="en">English</option><option value="kn">ಕನ್ನಡ (Kannada)</option><option value="hi">हिन्दी (Hindi)</option>
              </select>
            </Field>
            <div className="space-y-2 pt-6 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={f.notify_in_app} onChange={(e) => setF({ ...f, notify_in_app: e.target.checked })} /> In-app notifications</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={f.notify_sms} onChange={(e) => setF({ ...f, notify_sms: e.target.checked })} /> SMS notifications <DemoBadge label="simulated" /></label>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">SMS is simulated in this build - messages are logged, not sent. No SMS provider is connected.</p>
        </Card>
        {ng && (
          <Card title="NGO matching preferences">
            <div className="grid gap-4 md:grid-cols-3">
              <Field label="Service radius (km)" htmlFor="n-r"><input id="n-r" type="number" min={1} max={100} className={inputCls} value={ng.service_radius_km} onChange={(e) => setNg({ ...ng, service_radius_km: e.target.value })} /></Field>
              <Field label="Daily capacity" htmlFor="n-c"><input id="n-c" type="number" min={1} className={inputCls} value={ng.daily_capacity_portions} onChange={(e) => setNg({ ...ng, daily_capacity_portions: e.target.value })} /></Field>
              <div />
              <Field label="Pickups from (hour, IST)" htmlFor="n-s"><input id="n-s" type="number" min={0} max={23} className={inputCls} value={ng.pickup_start_hour} onChange={(e) => setNg({ ...ng, pickup_start_hour: e.target.value })} /></Field>
              <Field label="Pickups until (hour, IST)" htmlFor="n-e"><input id="n-e" type="number" min={0} max={24} className={inputCls} value={ng.pickup_end_hour} onChange={(e) => setNg({ ...ng, pickup_end_hour: e.target.value })} /></Field>
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={ng.accepts_veg} onChange={(e) => setNg({ ...ng, accepts_veg: e.target.checked })} /> Accepts veg</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={ng.accepts_non_veg} onChange={(e) => setNg({ ...ng, accepts_non_veg: e.target.checked })} /> Accepts non-veg</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={ng.has_vehicle} onChange={(e) => setNg({ ...ng, has_vehicle: e.target.checked })} /> Has vehicle</label>
            </div>
          </Card>
        )}
        {msg && <Notice tone="success">{msg}</Notice>}
        {err && <ErrorBox message={err} />}
        <Button type="submit" busy={busy}>Save settings</Button>
      </form>
    </div>
  );
}

export function NotFound() {
  return <Notice>Page not found.</Notice>;
}
