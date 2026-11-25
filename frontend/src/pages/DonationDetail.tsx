import { FormEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/Layout";
import { MapPoint, MapView } from "../components/Maps";
import { AuthImage, Button, Card, DemoBadge, ErrorBox, Field, inputCls, Loading, Notice, StatusBadge } from "../components/ui";
import type { ListingDetail, Storage, VolunteerOption } from "../types";
import { CATEGORY_LABEL, errText, fmtDateTime, fromLocalInput, LANG_LABEL, mapsDirections, STATUS_LABEL, STORAGE_LABEL, timeLeft, toLocalInput, useLoad } from "../utils";

interface Receipt {
  receipt_number: string; donor_organization: string; donor_name: string; ngo_name: string; volunteer_name: string; food_type: string;
  food_category: string; portions_reported: number; portions_collected: number; portions_delivered: number; prepared_at: string;
  picked_up_at: string | null; delivered_at: string; is_demo: boolean; statement: string;
}

function Timeline({ l }: { l: ListingDetail }) {
  return (
    <ol className="relative ml-3 border-l-2 border-leaf-200">
      {l.history.map((h) => (
        <li key={h.id} className="mb-4 ml-5">
          <span className="absolute -left-[9px] mt-1 h-4 w-4 rounded-full border-2 border-white bg-leaf-500" aria-hidden />
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={h.to_status} />
            <time className="text-xs text-slate-500">{fmtDateTime(h.created_at)}</time>
          </div>
          <div className="mt-1 text-sm text-slate-700">
            {h.note ?? STATUS_LABEL[h.to_status]}
            {h.actor_name && <span className="text-slate-500"> - {h.actor_name}{h.actor_role ? ` (${h.actor_role.toLowerCase()})` : ""}</span>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function ReceiptView({ id }: { id: number }) {
  const r = useLoad(() => api.get<Receipt>(`/api/listings/${id}/receipt`), [id]);
  if (r.loading) return <Loading />;
  if (r.error || !r.data) return <ErrorBox message={r.error ?? "Receipt unavailable"} />;
  const d = r.data;
  return (
    <div className="rounded-xl border-2 border-leaf-300 bg-cream-50 p-5 text-sm print:border-black" id="receipt">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-lg font-bold text-leaf-900">Donation receipt</div>
        {d.is_demo && <DemoBadge label="DEMO receipt" />}
      </div>
      <div className="mt-1 font-mono text-xs">{d.receipt_number}</div>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <div><dt className="text-xs text-slate-500">Donor</dt><dd>{d.donor_organization}</dd></div>
        <div><dt className="text-xs text-slate-500">Received by</dt><dd>{d.ngo_name}</dd></div>
        <div><dt className="text-xs text-slate-500">Food</dt><dd>{d.food_type} ({CATEGORY_LABEL[d.food_category] ?? d.food_category})</dd></div>
        <div><dt className="text-xs text-slate-500">Volunteer</dt><dd>{d.volunteer_name}</dd></div>
        <div><dt className="text-xs text-slate-500">Reported / collected / delivered</dt><dd className="font-semibold">{d.portions_reported} / {d.portions_collected} / {d.portions_delivered}</dd></div>
        <div><dt className="text-xs text-slate-500">Delivered at</dt><dd>{fmtDateTime(d.delivered_at)}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-slate-600">{d.statement}</p>
      <Button variant="secondary" className="mt-3 print:hidden" onClick={() => window.print()}>Print</Button>
    </div>
  );
}

function EditForFlagged({ l, onDone }: { l: ListingDetail; onDone: () => void }) {
  const [storage, setStorage] = useState<Storage | "">(l.storage_condition ?? "");
  const [allergens, setAllergens] = useState(l.allergens ?? "");
  const [deadline, setDeadline] = useState(toLocalInput(l.pickup_deadline));
  const [portions, setPortions] = useState(String(l.portions_reported));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.patch(`/api/listings/${l.id}`, {
        storage_condition: storage || null, allergens: allergens || null, pickup_deadline: fromLocalInput(deadline), portions_reported: Number(portions),
      });
      onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} className="space-y-3">
      <p className="text-sm text-slate-600">Fix the details below. The donation returns to draft so you can publish it again (it will be re-screened).</p>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Storage condition" htmlFor="e-st">
          <select id="e-st" className={inputCls} value={storage} onChange={(e) => setStorage(e.target.value as Storage | "")}>
            <option value="">Not specified</option>
            {Object.entries(STORAGE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Allergens" htmlFor="e-al"><input id="e-al" className={inputCls} value={allergens} onChange={(e) => setAllergens(e.target.value)} /></Field>
        <Field label="Pickup deadline (IST)" htmlFor="e-dl"><input id="e-dl" type="datetime-local" className={inputCls} value={deadline} onChange={(e) => setDeadline(e.target.value)} /></Field>
        <Field label="Portions" htmlFor="e-po"><input id="e-po" type="number" min={1} className={inputCls} value={portions} onChange={(e) => setPortions(e.target.value)} /></Field>
      </div>
      {err && <ErrorBox message={err} />}
      <Button type="submit" busy={busy}>Save changes</Button>
    </form>
  );
}

function Actions({ l, reload }: { l: ListingDetail; reload: () => void }) {
  const { me } = useAuth();
  const can = l.viewer_can;
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [volunteer, setVolunteer] = useState("");
  const [collected, setCollected] = useState(String(l.assignment?.collected_portions ?? l.portions_reported));
  const [delivered, setDelivered] = useState(String(l.assignment?.collected_portions ?? l.portions_reported));
  const [pickupNotes, setPickupNotes] = useState("");
  const [proof, setProof] = useState<File | null>(null);
  const [location, setLocation] = useState("");
  const [reason, setReason] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [showEdit, setShowEdit] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const vols = useLoad(() => (can.assign ? api.get<VolunteerOption[]>("/api/ngo/volunteers") : Promise.resolve([] as VolunteerOption[])), [can.assign]);

  const run = async (key: string, fn: () => Promise<unknown>, success?: string) => {
    setBusy(key);
    setErr(null);
    setMsg(null);
    try {
      await fn();
      if (success) setMsg(success);
      reload();
    } catch (e) {
      setErr(errText(e));
      reload();
    } finally {
      setBusy(null);
    }
  };

  const any = Object.entries(can).some(([k, v]) => v && k !== "edit");
  if (!any && !can.edit) return null;

  return (
    <Card title="Actions">
      <div className="space-y-4">
        {msg && <Notice tone="success">{msg}</Notice>}
        {err && <ErrorBox message={err} />}

        {can.publish && (
          <Button busy={busy === "publish"} onClick={() => run("publish", () => api.post(`/api/listings/${l.id}/publish`), "Published - safety screening and matching complete.")}>Publish and find NGOs</Button>
        )}
        {can.edit && l.status === "FLAGGED" && (
          showEdit ? <EditForFlagged l={l} onDone={() => { setShowEdit(false); reload(); }} /> : <Button variant="secondary" onClick={() => setShowEdit(true)}>Fix details and resubmit</Button>
        )}

        {(can.accept || can.reject) && (
          <div className="space-y-2">
            <p className="text-sm text-slate-600">Accepting reserves this donation for your organisation. The first NGO to accept gets it; you'll then see the exact address and donor contact.</p>
            <div className="flex flex-wrap gap-2">
              {can.accept && <Button busy={busy === "accept"} onClick={() => run("accept", () => api.post(`/api/ngo/listings/${l.id}/accept`), "Accepted! Assign a volunteer next.")}>Accept donation</Button>}
              {can.reject && (
                <>
                  <input aria-label="Reason for declining (optional)" placeholder="Reason (optional)" className={`${inputCls} max-w-xs`} value={reason} onChange={(e) => setReason(e.target.value)} />
                  <Button variant="secondary" busy={busy === "reject"} onClick={() => run("reject", () => api.post(`/api/ngo/listings/${l.id}/reject`, { reason: reason || null }), "Declined.")}>Decline</Button>
                </>
              )}
            </div>
          </div>
        )}

        {can.assign && (
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Assign a volunteer" htmlFor="vol">
              <select id="vol" className={inputCls} value={volunteer} onChange={(e) => setVolunteer(e.target.value)}>
                <option value="">Select volunteer...</option>
                {(vols.data ?? []).map((v) => (
                  <option key={v.user_id} value={v.user_id} disabled={!v.is_available}>
                    {v.full_name} {v.vehicle_type ? `(${v.vehicle_type})` : ""} {v.is_available ? `- ${v.active_assignments} active` : "- unavailable"}
                  </option>
                ))}
              </select>
            </Field>
            <Button disabled={!volunteer} busy={busy === "assign"} onClick={() => run("assign", () => api.post(`/api/ngo/listings/${l.id}/assign`, { volunteer_user_id: Number(volunteer) }), "Volunteer assigned and notified.")}>Assign</Button>
            {vols.data?.length === 0 && <p className="text-xs text-slate-500">Your organisation has no registered volunteers yet.</p>}
          </div>
        )}
        {can.unassign && <Button variant="secondary" busy={busy === "unassign"} onClick={() => run("unassign", () => api.post(`/api/ngo/listings/${l.id}/unassign`))}>Unassign volunteer</Button>}

        {can.confirm_pickup && l.assignment && (
          <form
            className="space-y-3 rounded-lg border border-cream-300 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData();
              fd.append("collected_portions", collected);
              if (pickupNotes) fd.append("notes", pickupNotes);
              if (proof) fd.append("proof", proof);
              run("pickup", () => api.upload(`/api/volunteer/assignments/${l.assignment!.id}/pickup`, fd), "Pickup confirmed. Head to the NGO next.");
            }}
          >
            <div className="font-semibold">Confirm pickup</div>
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="Portions actually collected" htmlFor="col" required><input id="col" type="number" min={0} required className={inputCls} value={collected} onChange={(e) => setCollected(e.target.value)} /></Field>
              <Field label="Notes" htmlFor="pn"><input id="pn" className={inputCls} value={pickupNotes} onChange={(e) => setPickupNotes(e.target.value)} placeholder="Condition, containers..." /></Field>
              <Field label="Proof photo" htmlFor="proof" hint="Optional, JPEG/PNG/WebP"><input id="proof" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="block w-full text-sm" onChange={(e) => setProof(e.target.files?.[0] ?? null)} /></Field>
            </div>
            <Button type="submit" busy={busy === "pickup"}>Confirm pickup</Button>
          </form>
        )}

        {can.confirm_delivery && l.assignment && (
          <form
            className="space-y-3 rounded-lg border border-cream-300 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              run("deliver", () => api.post(`/api/volunteer/assignments/${l.assignment!.id}/deliver`, { delivered_portions: Number(delivered), delivery_location: location || null }), "Delivery confirmed. Thank you!");
            }}
          >
            <div className="font-semibold">Confirm delivery</div>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Portions delivered" htmlFor="del" required hint={`Collected: ${l.assignment.collected_portions ?? "-"} (cannot exceed)`}>
                <input id="del" type="number" min={0} max={l.assignment.collected_portions ?? undefined} required className={inputCls} value={delivered} onChange={(e) => setDelivered(e.target.value)} />
              </Field>
              <Field label="Delivered to" htmlFor="dloc"><input id="dloc" className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Shelter / kitchen name" /></Field>
            </div>
            <Button type="submit" busy={busy === "deliver"}>Confirm delivery</Button>
          </form>
        )}

        {can.acknowledge && <Button busy={busy === "ack"} onClick={() => run("ack", () => api.post(`/api/ngo/listings/${l.id}/acknowledge`), "Receipt acknowledged.")}>Acknowledge receipt of food</Button>}

        {can.review_safety && (
          <div className="space-y-2 rounded-lg border border-chili-600/30 bg-chili-100/40 p-3">
            <div className="font-semibold">Admin safety review</div>
            <Field label="Review notes (required)" htmlFor="rn"><textarea id="rn" rows={2} className={inputCls} value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} /></Field>
            <div className="flex gap-2">
              <Button disabled={reviewNotes.trim().length < 3} busy={busy === "clear"} onClick={() => run("clear", () => api.post(`/api/admin/listings/${l.id}/safety-review`, { decision: "CLEARED", notes: reviewNotes }), "Cleared and matched.")}>Clear and match</Button>
              <Button variant="danger" disabled={reviewNotes.trim().length < 3} busy={busy === "rej"} onClick={() => run("rej", () => api.post(`/api/admin/listings/${l.id}/safety-review`, { decision: "REJECTED", notes: reviewNotes }), "Rejected.")}>Reject listing</Button>
            </div>
          </div>
        )}

        {can.receipt && (showReceipt ? <ReceiptView id={l.id} /> : <Button variant="secondary" onClick={() => setShowReceipt(true)}>View donation receipt</Button>)}

        {(me?.user.role === "DONOR" || me?.user.role === "ADMIN") && ["PUBLISHED", "MATCHED"].includes(l.status) && (
          <Button variant="ghost" busy={busy === "rematch"} onClick={() => run("rematch", () => api.post(`/api/listings/${l.id}/rematch`), "Matching re-run.")}>Re-run matching</Button>
        )}
        {can.cancel && (
          <Button
            variant="ghost"
            className="text-chili-700"
            busy={busy === "cancel"}
            onClick={() => window.confirm("Cancel this donation? NGOs and volunteers involved will be notified.") && run("cancel", () => api.post(`/api/listings/${l.id}/cancel`, { reason: null }), "Donation cancelled.")}
          >
            Cancel donation
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function DonationDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const nav = useNavigate();
  const q = useLoad(() => api.get<ListingDetail>(`/api/listings/${id}`), [id], 15000);
  if (q.loading && !q.data) return <Loading />;
  if (q.error && !q.data) return <ErrorBox message={q.error} onRetry={() => q.reload()} />;
  const l = q.data!;
  const left = timeLeft(l.pickup_deadline);
  const lastCheck = l.safety_checks[l.safety_checks.length - 1];
  const points: MapPoint[] = [{ lat: l.latitude, lng: l.longitude, label: l.location_precision === "exact" ? `Pickup: ${l.pickup_address}` : `${l.area}`, kind: "pickup", approximate: l.location_precision === "approximate" }];
  const vp = me?.volunteer_profile;
  const ngoPoint = me?.ngo_profile ?? null;
  if (ngoPoint) points.push({ lat: ngoPoint.latitude, lng: ngoPoint.longitude, label: ngoPoint.organization_name, kind: "ngo" });

  return (
    <>
      <PageTitle
        title={l.title}
        subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={l.status} />{l.is_demo && <DemoBadge />}{l.emergency && <span className="rounded-full bg-chili-600 px-2 py-0.5 text-xs font-bold text-white">Urgent</span>}<span>Donation #{l.id}</span></span>}
        actions={<button onClick={() => nav(-1)} className="text-sm text-leaf-700 hover:underline">← Back</button>}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Actions l={l} reload={() => q.reload(true)} />
          <Card title="Food details">
            <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div><dt className="text-xs text-slate-500">Food items</dt><dd>{l.food_type}</dd></div>
              <div><dt className="text-xs text-slate-500">Category</dt><dd>{CATEGORY_LABEL[l.food_category]}</dd></div>
              <div><dt className="text-xs text-slate-500">Portions reported</dt><dd className="font-semibold">{l.portions_reported}</dd></div>
              <div><dt className="text-xs text-slate-500">Prepared</dt><dd>{fmtDateTime(l.prepared_at)}</dd></div>
              <div><dt className="text-xs text-slate-500">Pickup deadline</dt><dd>{fmtDateTime(l.pickup_deadline)}{["DELIVERED", "CANCELLED", "EXPIRED"].includes(l.status) ? "" : <span className={`block text-xs ${left.minutes < 90 ? "font-semibold text-chili-700" : ""}`}>{left.label}</span>}</dd></div>
              <div><dt className="text-xs text-slate-500">Storage</dt><dd>{l.storage_condition ? STORAGE_LABEL[l.storage_condition] : <span className="text-chili-700">Not specified</span>}</dd></div>
              <div><dt className="text-xs text-slate-500">Allergens</dt><dd>{l.allergens ?? "Not declared"}</dd></div>
              <div><dt className="text-xs text-slate-500">Packaging</dt><dd>{l.packaging ?? "-"}</dd></div>
              <div><dt className="text-xs text-slate-500">Reported via</dt><dd>{l.source === "VOICE" ? `Voice (${LANG_LABEL[l.voice_language ?? ""] ?? l.voice_language})` : "Form"}</dd></div>
            </dl>
            {l.description && <p className="mt-3 text-sm text-slate-700">{l.description}</p>}
            {l.predicted_surplus_portions != null && <p className="mt-3 text-xs text-sky-800">PREDICTION saved by donor: ~{l.predicted_surplus_portions} portions (estimate only).</p>}
            {l.voice_transcript && <details className="mt-3 text-sm"><summary className="cursor-pointer text-leaf-700">Voice transcript</summary><p className="mt-1" lang={l.voice_language ?? undefined}>{l.voice_transcript}</p></details>}
            {l.has_image && <AuthImage path={`/api/listings/${l.id}/image`} alt={`Photo of ${l.food_type}`} className="mt-3 max-h-64 rounded-lg object-cover" />}
            <p className="mt-3 text-xs text-slate-500">{l.safety_disclaimer}</p>
          </Card>

          <Card title="Pickup">
            <div className="mb-3 grid gap-3 text-sm md:grid-cols-2">
              <div>
                <div className="text-xs text-slate-500">Location</div>
                {l.location_precision === "exact" ? <div>{l.pickup_address}</div> : <div>{l.area} <span className="text-xs text-slate-500">(approximate - exact address shared after you accept)</span></div>}
              </div>
              {l.donor_organization && (
                <div>
                  <div className="text-xs text-slate-500">Donor</div>
                  <div>{l.donor_organization}{l.donor_name ? ` - ${l.donor_name}` : ""}</div>
                  {l.donor_phone && <a href={`tel:${l.donor_phone.replace(/\s/g, "")}`} className="text-leaf-700 underline">{l.donor_phone}</a>}
                </div>
              )}
              {l.accepted_ngo_name && <div><div className="text-xs text-slate-500">Accepted by</div><div>{l.accepted_ngo_name}</div></div>}
              {l.assignment && <div><div className="text-xs text-slate-500">Volunteer</div><div>{l.assignment.volunteer_name} ({l.assignment.status.toLowerCase().replace("_", " ")})</div></div>}
            </div>
            <MapView points={points} />
            {l.location_precision === "exact" && (
              <a href={mapsDirections(l.latitude, l.longitude)} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block rounded-lg bg-leaf-600 px-4 py-2 text-sm font-semibold text-white hover:bg-leaf-700">
                Directions to pickup (Google Maps)
              </a>
            )}
            {vp && <p className="mt-2 text-xs text-slate-500">Drop-off: {vp.ngo_name}. See "My pickups" for NGO directions.</p>}
          </Card>

          {(l.assignment?.has_proof || l.delivery) && (
            <Card title="Collection and delivery">
              <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                <div><dt className="text-xs text-slate-500">Reported</dt><dd className="font-semibold">{l.portions_reported}</dd></div>
                <div><dt className="text-xs text-slate-500">Collected</dt><dd className="font-semibold">{l.assignment?.collected_portions ?? "-"}</dd></div>
                <div><dt className="text-xs text-slate-500">Delivered</dt><dd className="font-semibold text-leaf-700">{l.delivery?.delivered_portions ?? "pending"}</dd></div>
                <div><dt className="text-xs text-slate-500">NGO acknowledged</dt><dd>{l.delivery?.ngo_acknowledged_at ? fmtDateTime(l.delivery.ngo_acknowledged_at) : "Not yet"}</dd></div>
              </dl>
              {l.assignment?.collection_notes && <p className="mt-2 text-sm text-slate-600">Pickup notes: {l.assignment.collection_notes}</p>}
              {l.delivery?.receipt_number && <p className="mt-2 font-mono text-xs">Receipt {l.delivery.receipt_number}</p>}
              {l.assignment?.has_proof && <AuthImage path={`/api/listings/${l.id}/proof`} alt="Pickup proof photo" className="mt-3 max-h-56 rounded-lg object-cover" />}
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Timeline"><Timeline l={l} /></Card>
          {lastCheck && (
            <Card title="Safety screening">
              <div className="text-sm">
                Result: <strong className={lastCheck.result === "FLAGGED" ? "text-chili-700" : "text-leaf-700"}>{lastCheck.result === "ELIGIBLE" ? "Eligible for matching" : "Flagged for review"}</strong>
              </div>
              {lastCheck.issues.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm">
                  {lastCheck.issues.map((i) => <li key={i.code}><span className={i.severity === "BLOCKING" ? "font-semibold text-chili-700" : "font-semibold text-turmeric-700"}>{i.severity === "BLOCKING" ? "Blocking" : "Warning"}:</span> {i.message}</li>)}
                </ul>
              )}
              {lastCheck.review_decision && <p className="mt-2 text-sm">Admin review: <strong>{lastCheck.review_decision}</strong> - {lastCheck.review_notes}</p>}
            </Card>
          )}
          {l.my_match && (
            <Card title="Why you were matched">
              <div className="text-sm font-semibold text-leaf-700">Score {l.my_match.score}/100 · {l.my_match.distance_km} km away</div>
              <p className="mt-1 text-sm text-slate-700">{l.my_match.explanation}</p>
            </Card>
          )}
          {l.matches.length > 0 && (
            <Card title="Matched NGOs">
              <ol className="space-y-3">
                {l.matches.map((m) => (
                  <li key={m.ngo_id} className="text-sm">
                    <div className="flex justify-between font-semibold"><span>#{m.rank} {m.ngo_name}</span><span className="text-leaf-700">{m.score}</span></div>
                    <div className="text-xs text-slate-500">{m.ngo_area} · {m.distance_km} km{m.decision ? ` · ${m.decision.toLowerCase()}` : ""}</div>
                    <p className="mt-1 text-slate-600">{m.explanation}</p>
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-xs text-slate-500">Only administrator-verified NGOs are matched. Ranking uses distance, remaining capacity, pickup-time reachability, operating hours, food preference and vehicle availability.</p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
