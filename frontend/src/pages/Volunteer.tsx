import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/Layout";
import { MapView } from "../components/Maps";
import { Button, Card, Empty, ErrorBox, Loading, StatusBadge } from "../components/ui";
import type { VolunteerAssignment } from "../types";
import { errText, fmtDateTime, mapsDirections, timeLeft, useLoad } from "../utils";

export default function VolunteerDashboard() {
  const { me, refresh } = useAuth();
  const vp = me?.volunteer_profile;
  const q = useLoad(() => api.get<VolunteerAssignment[]>("/api/volunteer/assignments"), [], 15000);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    setBusy(true);
    try {
      await api.patch(`/api/me/availability?available=${!vp?.is_available}`);
      await refresh();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const active = (q.data ?? []).filter((a) => ["ASSIGNED", "PICKED_UP"].includes(a.assignment_status));
  const past = (q.data ?? []).filter((a) => !["ASSIGNED", "PICKED_UP"].includes(a.assignment_status));

  return (
    <>
      <PageTitle
        title="My pickups"
        subtitle={vp ? `Volunteering with ${vp.ngo_name}${vp.vehicle_type ? ` · ${vp.vehicle_type}` : ""}` : undefined}
        actions={vp && (
          <Button variant={vp.is_available ? "secondary" : "primary"} busy={busy} onClick={toggle} aria-pressed={vp.is_available}>
            {vp.is_available ? "I'm available ✓ (tap to go off duty)" : "Off duty (tap to become available)"}
          </Button>
        )}
      />
      {err && <ErrorBox message={err} />}
      {q.loading && !q.data && <Loading />}
      {q.error && <ErrorBox message={q.error} onRetry={() => q.reload()} />}
      <section className="space-y-4">
        {q.data && active.length === 0 && <Empty title="No active pickups">When your NGO assigns you a pickup it shows up here, and you'll get a notification.</Empty>}
        {active.map((a) => {
          const l = a.listing;
          const left = timeLeft(l.pickup_deadline);
          return (
            <Card key={a.assignment_id} title={<Link to={`/donations/${l.id}`} className="hover:underline">{l.title}</Link>} actions={<StatusBadge status={l.status} />}>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 text-sm">
                  <div><span className="text-slate-500">Food:</span> {l.food_type} · <strong>{l.portions_reported} portions</strong></div>
                  <div className={left.minutes < 60 ? "font-semibold text-chili-700" : ""}><span className="text-slate-500">Pick up by:</span> {fmtDateTime(l.pickup_deadline)} ({left.label})</div>
                  <div><span className="text-slate-500">Pickup:</span> {l.pickup_address}</div>
                  <div><span className="text-slate-500">Donor contact:</span> {l.donor_name} {l.donor_phone && <a className="text-leaf-700 underline" href={`tel:${l.donor_phone.replace(/\s/g, "")}`}>{l.donor_phone}</a>}</div>
                  <div><span className="text-slate-500">Drop at:</span> {a.ngo_name} - {a.ngo_address}</div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <a className="rounded-lg bg-leaf-600 px-3 py-2 text-sm font-semibold text-white hover:bg-leaf-700" href={mapsDirections(l.latitude, l.longitude)} target="_blank" rel="noopener noreferrer">Directions to pickup</a>
                    <a className="rounded-lg bg-white px-3 py-2 text-sm font-semibold text-leaf-800 ring-1 ring-leaf-300 hover:bg-leaf-50" href={mapsDirections(a.ngo_latitude, a.ngo_longitude)} target="_blank" rel="noopener noreferrer">Directions to NGO</a>
                    <Link className="rounded-lg bg-turmeric-100 px-3 py-2 text-sm font-semibold text-turmeric-700 hover:bg-turmeric-100/70" to={`/donations/${l.id}`}>
                      {a.assignment_status === "ASSIGNED" ? "Confirm pickup →" : "Confirm delivery →"}
                    </Link>
                  </div>
                </div>
                <MapView height="h-56" points={[{ lat: l.latitude, lng: l.longitude, label: "Pickup", kind: "pickup" }, { lat: a.ngo_latitude, lng: a.ngo_longitude, label: a.ngo_name, kind: "ngo" }]} />
              </div>
            </Card>
          );
        })}
      </section>
      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-leaf-900">Past pickups</h2>
        {past.length === 0 ? (
          <Empty title="No past pickups yet" />
        ) : (
          <ul className="divide-y divide-cream-200 rounded-xl border border-cream-300 bg-white">
            {past.map((a) => (
              <li key={a.assignment_id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                <Link to={`/donations/${a.listing.id}`} className="font-medium text-leaf-800 hover:underline">{a.listing.title}</Link>
                <span className="text-slate-500">{a.collected_portions != null ? `${a.collected_portions} collected · ` : ""}{fmtDateTime(a.delivered_at ?? a.picked_up_at)}</span>
                <StatusBadge status={a.assignment_status === "DELIVERED" ? "DELIVERED" : a.listing.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
