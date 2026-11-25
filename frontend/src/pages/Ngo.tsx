import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/Layout";
import { ListingCard } from "../components/ListingCard";
import { MapView } from "../components/Maps";
import { Empty, ErrorBox, inputCls, Loading, Notice, Stat } from "../components/ui";
import type { Listing } from "../types";
import { CATEGORY_LABEL, useLoad } from "../utils";

interface NgoStats {
  verification_status: string; daily_capacity: number; capacity_used_today: number; capacity_remaining_today: number;
  open_matches: number; in_progress: number; portions_received: number;
}

export default function NgoDashboard() {
  const { me } = useAuth();
  const ngo = me?.ngo_profile;
  const verified = ngo?.verification_status === "VERIFIED";
  const [category, setCategory] = useState("");
  const [maxKm, setMaxKm] = useState("");
  const [minPortions, setMinPortions] = useState("");
  const qs = new URLSearchParams();
  if (category) qs.set("category", category);
  if (maxKm) qs.set("max_distance_km", maxKm);
  if (minPortions) qs.set("min_portions", minPortions);
  const stats = useLoad(() => api.get<NgoStats>("/api/ngo/stats"), [], 15000);
  const avail = useLoad(() => (verified ? api.get<Listing[]>(`/api/ngo/listings/available?${qs}`) : Promise.resolve([])), [verified, category, maxKm, minPortions], 15000);
  const accepted = useLoad(() => (verified ? api.get<Listing[]>("/api/ngo/listings/accepted") : Promise.resolve([])), [verified], 15000);

  if (!ngo) return <Loading />;
  const active = (accepted.data ?? []).filter((l) => ["ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP"].includes(l.status));
  const done = (accepted.data ?? []).filter((l) => !["ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP"].includes(l.status));

  return (
    <>
      <PageTitle title={ngo.organization_name} subtitle={`${ngo.area} · serves within ${ngo.service_radius_km} km · ${ngo.accepts_veg && ngo.accepts_non_veg ? "veg & non-veg" : ngo.accepts_veg ? "veg only" : "non-veg only"} · pickups ${ngo.pickup_start_hour}:00–${ngo.pickup_end_hour}:00`} />
      {!verified && (
        <div className="mb-6">
          <Notice tone="warning">
            <strong>Verification {ngo.verification_status.toLowerCase()}.</strong> A FestivePlate administrator must verify your organisation before you can see or accept donations.
            {ngo.verification_notes && <span className="block">Admin notes: {ngo.verification_notes}</span>}
          </Notice>
        </div>
      )}
      {stats.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Capacity left today" value={`${stats.data.capacity_remaining_today} / ${stats.data.daily_capacity}`} />
          <Stat label="Open matches" value={stats.data.open_matches} />
          <Stat label="In progress" value={stats.data.in_progress} />
          <Stat label="Portions received" value={stats.data.portions_received} hint="Confirmed deliveries" />
        </div>
      )}
      {verified && (
        <div className="space-y-8">
          <section>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-lg font-semibold text-leaf-900">Available donations matched to you</h2>
              <div className="flex flex-wrap gap-2">
                <select aria-label="Filter by food category" className={`${inputCls} w-40`} value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="">All food types</option>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <input aria-label="Maximum distance in km" placeholder="Max km" type="number" min={1} className={`${inputCls} w-24`} value={maxKm} onChange={(e) => setMaxKm(e.target.value)} />
                <input aria-label="Minimum portions" placeholder="Min portions" type="number" min={1} className={`${inputCls} w-32`} value={minPortions} onChange={(e) => setMinPortions(e.target.value)} />
              </div>
            </div>
            {avail.loading && !avail.data && <Loading />}
            {avail.error && <ErrorBox message={avail.error} onRetry={() => avail.reload()} />}
            {avail.data && avail.data.length > 0 && (
              <div className="mb-4">
                <MapView height="h-56" points={[{ lat: ngo.latitude, lng: ngo.longitude, label: ngo.organization_name, kind: "ngo" }, ...avail.data.map((l) => ({ lat: l.latitude, lng: l.longitude, label: `${l.title} (${l.portions_reported} portions)`, approximate: true }))]} />
              </div>
            )}
            {avail.data && avail.data.length === 0 ? (
              <Empty title="No open donations matched right now">New matches appear here automatically and you'll get a notification.</Empty>
            ) : (
              <div className="grid gap-3">
                {(avail.data ?? []).map((l) => (
                  <ListingCard
                    key={l.id}
                    l={l}
                    extra={l.my_match && (
                      <div className="rounded-lg bg-leaf-50 p-2 text-sm">
                        <span className="font-semibold text-leaf-800">{l.my_match.distance_km} km · match score {l.my_match.score}</span>
                        <span className="block text-slate-600">{l.my_match.explanation}</span>
                      </div>
                    )}
                  />
                ))}
              </div>
            )}
          </section>
          <section>
            <h2 className="mb-3 text-lg font-semibold text-leaf-900">Accepted - in progress</h2>
            {active.length === 0 ? <Empty title="Nothing in progress" /> : <div className="grid gap-3">{active.map((l) => <ListingCard key={l.id} l={l} />)}</div>}
          </section>
          <section>
            <h2 className="mb-3 text-lg font-semibold text-leaf-900">Completed and closed</h2>
            {done.length === 0 ? <Empty title="No completed donations yet" /> : <div className="grid gap-3">{done.map((l) => <ListingCard key={l.id} l={l} />)}</div>}
          </section>
        </div>
      )}
    </>
  );
}
