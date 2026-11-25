import { Link } from "react-router-dom";
import { api } from "../api";
import { homeFor, useAuth } from "../auth";
import { DemoBadge, Stat } from "../components/ui";
import type { Impact } from "../types";
import { useLoad } from "../utils";

const STEPS = [
  { t: "Report surplus", d: "Donors type or speak (Kannada, Hindi or English) what's left over. AI drafts the listing; the donor confirms every field." },
  { t: "Safety screening", d: "Rule-based checks flag missing storage info, expired deadlines or unsafe hold times for admin review. We never certify food as safe." },
  { t: "Match verified NGOs", d: "Only admin-verified NGOs are ranked - by distance, capacity, pickup hours and preferences - with a plain-language reason for each match." },
  { t: "Pickup and delivery", d: "The first NGO to accept gets it (no double booking). A volunteer records collected and delivered portions separately." },
];

export default function Landing() {
  const { me } = useAuth();
  const { data } = useLoad(() => api.get<Impact>("/api/impact/public"));
  return (
    <div className="space-y-12">
      <section className="grid items-center gap-8 rounded-3xl bg-gradient-to-br from-leaf-600 to-leaf-800 p-8 text-white shadow-lg md:grid-cols-2 md:p-12">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-leaf-100">Bengaluru food rescue</p>
          <h1 className="mt-2 text-4xl font-extrabold leading-tight md:text-5xl">Every wedding feast deserves a second plate.</h1>
          <p className="mt-4 text-lg text-leaf-50">
            FestivePlate helps wedding halls, caterers and restaurants get surplus food to verified NGOs before it goes to waste - fast, safely, and with proof of delivery.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {me ? (
              <Link to={homeFor(me.user.role)} className="rounded-lg bg-white px-5 py-2.5 font-semibold text-leaf-800 hover:bg-cream-100">Go to my dashboard</Link>
            ) : (
              <>
                <Link to="/register" className="rounded-lg bg-white px-5 py-2.5 font-semibold text-leaf-800 hover:bg-cream-100">Join FestivePlate</Link>
                <Link to="/login" className="rounded-lg px-5 py-2.5 font-semibold text-white ring-1 ring-white/60 hover:bg-white/10">Try the demo</Link>
              </>
            )}
          </div>
        </div>
        <div className="rounded-2xl bg-white/10 p-6 ring-1 ring-white/20">
          <div className="mb-3 flex items-center gap-2 text-sm text-leaf-50">Live platform totals <DemoBadge label="includes demo data" /></div>
          {data && data.enabled !== false ? (
            <div className="grid grid-cols-2 gap-3 text-slate-800">
              <Stat label="Portions delivered" value={data.delivered_portions} hint="Confirmed deliveries only" />
              <Stat label="Completed donations" value={data.completed_donations} />
              <Stat label="Portions collected" value={data.collected_portions} />
              <Stat label="Verified NGOs" value={data.verified_ngos} />
            </div>
          ) : (
            <p className="text-sm text-leaf-50">Impact statistics are currently hidden.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="how">
        <h2 id="how" className="mb-4 text-2xl font-bold text-leaf-900">How it works</h2>
        <ol className="grid gap-4 md:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.t} className="rounded-xl border border-cream-300 bg-white p-5 shadow-sm">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-leaf-100 font-bold text-leaf-800">{i + 1}</div>
              <h3 className="mt-3 font-semibold text-leaf-900">{s.t}</h3>
              <p className="mt-1 text-sm text-slate-600">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          { t: "For donors", d: "Wedding halls, hotels, caterers and restaurants: report in under a minute, by voice if you like, and get a delivery receipt." },
          { t: "For NGOs", d: "See matched surplus near you with time left, portions and food type. Accept, assign a volunteer, confirm receipt." },
          { t: "For volunteers", d: "Get pickup and drop directions, record what you collected and delivered, and upload proof photos." },
        ].map((c) => (
          <div key={c.t} className="rounded-xl bg-cream-100 p-5">
            <h3 className="font-semibold text-leaf-900">{c.t}</h3>
            <p className="mt-1 text-sm text-slate-700">{c.d}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
