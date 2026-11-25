import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { PageTitle } from "../components/Layout";
import { Button, Card, cx, DemoBadge, Empty, ErrorBox, inputCls, Loading, Notice, Stat, StatusBadge } from "../components/ui";
import type { FlagRow, Listing, NgoProfile, SafetyIssue, User } from "../types";
import { errText, fmtDateTime, STATUS_LABEL, useLoad } from "../utils";

interface Analytics {
  listings_by_status: Record<string, number>; users_by_role: Record<string, number>; ngos_by_verification: Record<string, number>;
  top_areas: { area: string; listings: number }[]; open_safety_flags: number; total_safety_flags_raised: number; failed_notifications: number;
}

const TABS = ["Overview", "NGO verification", "Safety flags", "Donations", "Users", "Feature flags", "Audit log"] as const;
type Tab = (typeof TABS)[number];

function Overview() {
  const q = useLoad(() => api.get<Analytics>("/api/admin/analytics"), [], 20000);
  if (q.loading) return <Loading />;
  if (q.error || !q.data) return <ErrorBox message={q.error ?? ""} onRetry={() => q.reload()} />;
  const a = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Open safety flags" value={a.open_safety_flags} />
        <Stat label="NGOs pending verification" value={a.ngos_by_verification.PENDING ?? 0} />
        <Stat label="Failed notifications" value={a.failed_notifications} />
        <Stat label="Total users" value={Object.values(a.users_by_role).reduce((s, n) => s + n, 0)} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Donations by status">
          <ul className="space-y-1 text-sm">{Object.entries(a.listings_by_status).map(([k, v]) => <li key={k} className="flex justify-between"><StatusBadge status={k} /><span className="font-semibold">{v}</span></li>)}</ul>
        </Card>
        <Card title="Users by role">
          <ul className="space-y-1 text-sm">{Object.entries(a.users_by_role).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="font-semibold">{v}</span></li>)}</ul>
        </Card>
        <Card title="Top areas">
          <ul className="space-y-1 text-sm">{a.top_areas.map((t) => <li key={t.area} className="flex justify-between"><span>{t.area}</span><span className="font-semibold">{t.listings}</span></li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

function NgoVerification() {
  const [filter, setFilter] = useState("PENDING");
  const q = useLoad(() => api.get<NgoProfile[]>(`/api/admin/ngos${filter ? `?verification_status=${filter}` : ""}`), [filter]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const decide = async (id: number, decision: string) => {
    setErr(null);
    try {
      await api.post(`/api/admin/ngos/${id}/verify`, { decision, notes: notes[id] || null });
      q.reload(true);
    } catch (e) {
      setErr(errText(e));
    }
  };
  return (
    <div className="space-y-3">
      <select aria-label="Filter NGOs by verification status" className={`${inputCls} w-48`} value={filter} onChange={(e) => setFilter(e.target.value)}>
        <option value="">All</option><option value="PENDING">Pending</option><option value="VERIFIED">Verified</option><option value="REJECTED">Rejected</option><option value="SUSPENDED">Suspended</option>
      </select>
      {err && <ErrorBox message={err} />}
      {q.loading && <Loading />}
      {q.data?.length === 0 && <Empty title="No NGOs in this state" />}
      {q.data?.map((n) => (
        <Card key={n.id} title={n.organization_name} actions={<span className={cx("rounded-full px-2 py-0.5 text-xs font-semibold", n.verification_status === "VERIFIED" ? "bg-leaf-100 text-leaf-800" : n.verification_status === "PENDING" ? "bg-turmeric-100 text-turmeric-700" : "bg-chili-100 text-chili-700")}>{n.verification_status}</span>}>
          <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <div><dt className="text-xs text-slate-500">Registration no.</dt><dd>{n.registration_number}</dd></div>
            <div><dt className="text-xs text-slate-500">Contact</dt><dd>{n.contact_person}</dd></div>
            <div><dt className="text-xs text-slate-500">Area</dt><dd>{n.area} ({n.service_radius_km} km)</dd></div>
            <div><dt className="text-xs text-slate-500">Capacity / day</dt><dd>{n.daily_capacity_portions}</dd></div>
            <div className="col-span-2"><dt className="text-xs text-slate-500">Address</dt><dd>{n.address}</dd></div>
            <div><dt className="text-xs text-slate-500">Registered</dt><dd>{fmtDateTime(n.created_at)}</dd></div>
          </dl>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input aria-label={`Notes for ${n.organization_name}`} placeholder="Verification notes (documents checked, visit date...)" className={`${inputCls} max-w-md`} value={notes[n.id] ?? ""} onChange={(e) => setNotes({ ...notes, [n.id]: e.target.value })} />
            {n.verification_status !== "VERIFIED" && <Button onClick={() => decide(n.id, "VERIFIED")}>Verify</Button>}
            {n.verification_status === "PENDING" && <Button variant="danger" onClick={() => decide(n.id, "REJECTED")}>Reject</Button>}
            {n.verification_status === "VERIFIED" && <Button variant="danger" onClick={() => decide(n.id, "SUSPENDED")}>Suspend</Button>}
          </div>
        </Card>
      ))}
    </div>
  );
}

function SafetyFlags() {
  const q = useLoad(() => api.get<{ listing: Listing; issues: SafetyIssue[] }[]>("/api/admin/safety-flags"), [], 20000);
  if (q.loading) return <Loading />;
  if (q.error) return <ErrorBox message={q.error} onRetry={() => q.reload()} />;
  if (!q.data?.length) return <Empty title="No donations awaiting safety review" />;
  return (
    <div className="space-y-3">
      <Notice>Flagged donations are excluded from matching until reviewed. Open a donation to clear or reject it. Review decisions are recorded in the audit log.</Notice>
      {q.data.map(({ listing: l, issues }) => (
        <Card key={l.id} title={<Link to={`/donations/${l.id}`} className="hover:underline">{l.title}</Link>} actions={<span className="flex gap-1">{l.is_demo && <DemoBadge />}<StatusBadge status={l.status} /></span>}>
          <div className="text-sm text-slate-600">{l.donor_organization} · {l.area} · {l.portions_reported} portions · deadline {fmtDateTime(l.pickup_deadline)}</div>
          <ul className="mt-2 space-y-1 text-sm">{issues.map((i) => <li key={i.code}><strong className={i.severity === "BLOCKING" ? "text-chili-700" : "text-turmeric-700"}>{i.severity}</strong> - {i.message}</li>)}</ul>
          <Link to={`/donations/${l.id}`} className="mt-2 inline-block text-sm font-semibold text-leaf-700 hover:underline">Review →</Link>
        </Card>
      ))}
    </div>
  );
}

function Donations() {
  const [status, setStatus] = useState("");
  const q = useLoad(() => api.get<Listing[]>(`/api/admin/listings${status ? `?status=${status}` : ""}`), [status]);
  return (
    <div className="space-y-3">
      <select aria-label="Filter donations by status" className={`${inputCls} w-56`} value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>
        {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      {q.loading && <Loading />}
      {q.error && <ErrorBox message={q.error} />}
      {q.data?.length === 0 && <Empty title="No donations" />}
      {!!q.data?.length && (
        <div className="overflow-x-auto rounded-xl border border-cream-300 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-cream-100 text-left text-xs uppercase text-slate-600"><tr><th className="p-2">#</th><th className="p-2">Title</th><th className="p-2">Donor</th><th className="p-2">Area</th><th className="p-2">Portions</th><th className="p-2">Status</th><th className="p-2">Created</th></tr></thead>
            <tbody>
              {q.data.map((l) => (
                <tr key={l.id} className="border-t border-cream-200">
                  <td className="p-2">{l.id}</td>
                  <td className="p-2"><Link to={`/donations/${l.id}`} className="text-leaf-800 hover:underline">{l.title}</Link> {l.is_demo && <DemoBadge />}</td>
                  <td className="p-2">{l.donor_organization}</td>
                  <td className="p-2">{l.area}</td>
                  <td className="p-2">{l.portions_reported}</td>
                  <td className="p-2"><StatusBadge status={l.status} /></td>
                  <td className="p-2 whitespace-nowrap">{fmtDateTime(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Users() {
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const q = useLoad(() => api.get<User[]>(`/api/admin/users?${new URLSearchParams({ ...(search && { q: search }), ...(role && { role }) })}`), [search, role]);
  const toggle = async (u: User) => {
    if (!window.confirm(`${u.is_active ? "Deactivate" : "Reactivate"} ${u.full_name}?`)) return;
    await api.patch(`/api/admin/users/${u.id}`, { is_active: !u.is_active });
    q.reload(true);
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input aria-label="Search users" placeholder="Search name or email" className={`${inputCls} max-w-xs`} value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Filter by role" className={`${inputCls} w-40`} value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">All roles</option><option>DONOR</option><option>NGO</option><option>VOLUNTEER</option><option>ADMIN</option>
        </select>
      </div>
      {q.loading && <Loading />}
      {!!q.data?.length && (
        <div className="overflow-x-auto rounded-xl border border-cream-300 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-cream-100 text-left text-xs uppercase text-slate-600"><tr><th className="p-2">Name</th><th className="p-2">Email</th><th className="p-2">Role</th><th className="p-2">Language</th><th className="p-2">Status</th><th className="p-2"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {q.data.map((u) => (
                <tr key={u.id} className="border-t border-cream-200">
                  <td className="p-2">{u.full_name} {u.is_demo && <DemoBadge />}</td>
                  <td className="p-2">{u.email}</td>
                  <td className="p-2">{u.role}</td>
                  <td className="p-2">{u.preferred_language}</td>
                  <td className="p-2">{u.is_active ? "Active" : <span className="text-chili-700">Deactivated</span>}</td>
                  <td className="p-2">{u.role !== "ADMIN" && <Button variant="ghost" onClick={() => toggle(u)}>{u.is_active ? "Deactivate" : "Reactivate"}</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface FlagsResp {
  connection: { configured: boolean; connected: boolean; message: string; last_error?: string | null };
  flags: FlagRow[];
  audit: { flag_name: string; old_value: boolean | null; new_value: boolean | null; source: string; reason: string | null; changed_by: string | number | null; created_at: string }[];
}

function FeatureFlags() {
  const q = useLoad(() => api.get<FlagsResp>("/api/admin/flags"), []);
  const [err, setErr] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const setFlag = async (name: string, enabled: boolean) => {
    setErr(null);
    try {
      await api.put(`/api/admin/flags/${name}/override`, { enabled, reason: reason || null });
      q.reload(true);
    } catch (e) {
      setErr(errText(e));
    }
  };
  const clear = async (name: string) => {
    await api.del(`/api/admin/flags/${name}/override`);
    q.reload(true);
  };
  if (q.loading) return <Loading />;
  if (q.error || !q.data) return <ErrorBox message={q.error ?? ""} />;
  const c = q.data.connection;
  return (
    <div className="space-y-4">
      <Notice tone={c.connected ? "success" : c.configured ? "warning" : "info"}>
        <strong>Flagsmith: {c.connected ? "connected" : c.configured ? "configured but not reachable" : "not configured"}.</strong> {c.message}
        <span className="block text-xs">Resolution order: local admin override → Flagsmith value → safe default.</span>
      </Notice>
      {err && <ErrorBox message={err} />}
      <input aria-label="Reason for change" placeholder="Reason for change (recorded in audit)" className={`${inputCls} max-w-md`} value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="overflow-x-auto rounded-xl border border-cream-300 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-cream-100 text-left text-xs uppercase text-slate-600"><tr><th className="p-2">Flag</th><th className="p-2">Effective</th><th className="p-2">Source</th><th className="p-2">Default</th><th className="p-2">Flagsmith</th><th className="p-2">Override</th></tr></thead>
          <tbody>
            {q.data.flags.map((f) => (
              <tr key={f.name} className="border-t border-cream-200 align-top">
                <td className="p-2"><code className="font-semibold">{f.name}</code><div className="text-xs text-slate-500">{f.description}</div></td>
                <td className="p-2">{f.enabled ? <span className="font-semibold text-leaf-700">ON</span> : <span className="font-semibold text-slate-500">OFF</span>}</td>
                <td className="p-2">{f.source.replace("_", " ")}</td>
                <td className="p-2">{f.default ? "on" : "off"}</td>
                <td className="p-2">{f.flagsmith_value == null ? "-" : f.flagsmith_value ? "on" : "off"}</td>
                <td className="p-2">
                  <div className="flex flex-wrap gap-1">
                    <Button variant={f.local_override === true ? "primary" : "secondary"} className="px-2 py-1" onClick={() => setFlag(f.name, true)} aria-pressed={f.local_override === true}>On</Button>
                    <Button variant={f.local_override === false ? "danger" : "secondary"} className="px-2 py-1" onClick={() => setFlag(f.name, false)} aria-pressed={f.local_override === false}>Off</Button>
                    {f.local_override != null && <Button variant="ghost" className="px-2 py-1" onClick={() => clear(f.name)}>Clear</Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Card title="Flag change history">
        {q.data.audit.length === 0 ? <p className="text-sm text-slate-500">No changes yet.</p> : (
          <ul className="space-y-1 text-sm">
            {q.data.audit.map((a, i) => (
              <li key={i}><time className="text-slate-500">{fmtDateTime(a.created_at)}</time> - <code>{a.flag_name}</code> {String(a.old_value)} → {String(a.new_value)} ({a.source}){a.changed_by ? ` by ${a.changed_by}` : ""}{a.reason ? ` - ${a.reason}` : ""}</li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function AuditLog() {
  const q = useLoad(() => api.get<{ id: number; actor: string | null; action: string; entity_type: string; entity_id: number | null; details: Record<string, unknown>; created_at: string }[]>("/api/admin/audit-logs?limit=200"), []);
  if (q.loading) return <Loading />;
  if (q.error) return <ErrorBox message={q.error} />;
  return (
    <div className="overflow-x-auto rounded-xl border border-cream-300 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-cream-100 text-left text-xs uppercase text-slate-600"><tr><th className="p-2">When</th><th className="p-2">Actor</th><th className="p-2">Action</th><th className="p-2">Entity</th><th className="p-2">Details</th></tr></thead>
        <tbody>
          {(q.data ?? []).map((a) => (
            <tr key={a.id} className="border-t border-cream-200">
              <td className="whitespace-nowrap p-2">{fmtDateTime(a.created_at)}</td>
              <td className="p-2">{a.actor ?? "system"}</td>
              <td className="p-2"><code>{a.action}</code></td>
              <td className="p-2">{a.entity_type}{a.entity_id != null ? ` #${a.entity_id}` : ""}</td>
              <td className="p-2 text-xs text-slate-600">{Object.keys(a.details).length ? JSON.stringify(a.details) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <>
      <PageTitle title="Administration" subtitle="Verify NGOs, review safety flags, manage users and feature flags." actions={<Link to="/admin/system" className="text-sm font-semibold text-leaf-700 hover:underline">System health →</Link>} />
      <div role="tablist" aria-label="Admin sections" className="mb-4 flex flex-wrap gap-1 border-b border-cream-300">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cx("-mb-px border-b-2 px-3 py-2 text-sm font-medium", tab === t ? "border-leaf-600 text-leaf-900" : "border-transparent text-slate-600 hover:text-leaf-800")}>
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "Overview" && <Overview />}
        {tab === "NGO verification" && <NgoVerification />}
        {tab === "Safety flags" && <SafetyFlags />}
        {tab === "Donations" && <Donations />}
        {tab === "Users" && <Users />}
        {tab === "Feature flags" && <FeatureFlags />}
        {tab === "Audit log" && <AuditLog />}
      </div>
    </>
  );
}
