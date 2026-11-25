import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/Layout";
import { ListingCard } from "../components/ListingCard";
import { MapPicker } from "../components/Maps";
import { Button, Card, Empty, ErrorBox, Field, inputCls, Loading, Notice, SimulatedBanner, Stat } from "../components/ui";
import type { FoodCategory, Listing, ListingDetail, Prediction, PublishResult, Storage, VoiceResult } from "../types";
import { CATEGORY_LABEL, errText, fromLocalInput, LANG_LABEL, STORAGE_LABEL, toLocalInput, useLoad } from "../utils";

interface Stats {
  active_donations: number; pending_pickups: number; completed_donations: number; portions_delivered: number; portions_collected: number; note: string;
}

const ACTIVE = ["DRAFT", "PUBLISHED", "MATCHED", "ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP", "FLAGGED"];

export function DonorDashboard() {
  const listings = useLoad(() => api.get<Listing[]>("/api/listings/mine"), [], 15000);
  const stats = useLoad(() => api.get<Stats>("/api/listings/mine/stats"), [], 15000);
  const active = (listings.data ?? []).filter((l) => ACTIVE.includes(l.status));
  const past = (listings.data ?? []).filter((l) => !ACTIVE.includes(l.status));
  return (
    <>
      <PageTitle title="My donations" subtitle="Track every surplus report from listing to confirmed delivery." actions={<Link to="/donor/new" className="rounded-lg bg-leaf-600 px-4 py-2 text-sm font-semibold text-white hover:bg-leaf-700">+ Report surplus food</Link>} />
      {stats.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Active donations" value={stats.data.active_donations} />
          <Stat label="Pending pickups" value={stats.data.pending_pickups} />
          <Stat label="Completed" value={stats.data.completed_donations} />
          <Stat label="Portions delivered" value={stats.data.portions_delivered} hint={stats.data.note} />
        </div>
      )}
      {listings.loading && <Loading />}
      {listings.error && <ErrorBox message={listings.error} onRetry={() => listings.reload()} />}
      {listings.data && (
        <div className="space-y-8">
          <section>
            <h2 className="mb-3 text-lg font-semibold text-leaf-900">Active</h2>
            {active.length === 0 ? (
              <Empty title="No active donations">Have surplus food? <Link to="/donor/new" className="text-leaf-700 underline">Report it</Link> - by voice or form.</Empty>
            ) : (
              <div className="grid gap-3">{active.map((l) => <ListingCard key={l.id} l={l} />)}</div>
            )}
          </section>
          <section>
            <h2 className="mb-3 text-lg font-semibold text-leaf-900">History</h2>
            {past.length === 0 ? <Empty title="No past donations yet" /> : <div className="grid gap-3">{past.map((l) => <ListingCard key={l.id} l={l} />)}</div>}
          </section>
        </div>
      )}
    </>
  );
}

// ---------------- Voice recorder ----------------

function VoiceReporter({ onResult }: { onResult: (r: VoiceResult) => void }) {
  const [lang, setLang] = useState<"kn" | "hi" | "en">("kn");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const supported = typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); rec.current?.stream.getTracks().forEach((t) => t.stop()); }, []);

  const send = async (blob: Blob) => {
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("audio", blob, `report.${blob.type.includes("mp4") ? "m4a" : "webm"}`);
      fd.append("language", lang);
      onResult(await api.upload<VoiceResult>("/api/ai/voice/transcribe", fd));
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        send(new Blob(chunks.current, { type: mr.mimeType || "audio/webm" }));
      };
      mr.start();
      rec.current = mr;
      setRecording(true);
      setSeconds(0);
      timer.current = window.setInterval(() => setSeconds((s) => { if (s >= 59) stop(); return s + 1; }), 1000);
    } catch {
      setErr("Microphone access was denied or is unavailable. You can use the demo sample or fill the form manually.");
    }
  };

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    setRecording(false);
    if (rec.current?.state === "recording") rec.current.stop();
  };

  const demo = async () => {
    setBusy(true);
    setErr(null);
    try {
      onResult(await api.post<VoiceResult>(`/api/ai/voice/demo?language=${lang}`));
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Report by voice" className="border-leaf-200 bg-leaf-50/40">
      <p className="mb-3 text-sm text-slate-600">
        Speak naturally - what food, how many portions, when it was cooked, how it's stored, and when it must be picked up. AI fills in a draft; <strong>you review and confirm every field</strong> before anything is published.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Language" htmlFor="vlang">
          <select id="vlang" className={inputCls} value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} disabled={recording || busy}>
            {(["kn", "hi", "en"] as const).map((l) => <option key={l} value={l}>{LANG_LABEL[l]}</option>)}
          </select>
        </Field>
        {supported &&
          (recording ? (
            <Button variant="danger" onClick={stop} type="button">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-white" aria-hidden /> Stop recording ({seconds}s)
            </Button>
          ) : (
            <Button onClick={start} type="button" busy={busy}>🎙️ Start recording</Button>
          ))}
        <Button variant="secondary" onClick={demo} type="button" disabled={recording} busy={busy}>Use DEMO sample report</Button>
      </div>
      {!supported && <p className="mt-2 text-xs text-slate-500">This browser can't record audio. Use the demo sample or the form below.</p>}
      <div aria-live="polite" className="mt-3">{busy && <Loading label="Transcribing and extracting details..." />}{err && <ErrorBox message={err} />}</div>
    </Card>
  );
}

// ---------------- Prediction ----------------

function PredictionPanel({ onUse }: { onUse: (n: number) => void }) {
  const [planned, setPlanned] = useState("500");
  const [expected, setExpected] = useState("450");
  const [p, setP] = useState<Prediction | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setErr(null);
    try {
      setP(await api.post<Prediction>("/api/ai/predict-surplus", { event_type: "WEDDING", planned_servings: Number(planned), expected_attendance: Number(expected) }));
    } catch (e) {
      setErr(errText(e));
    }
  };
  return (
    <details className="rounded-xl border border-cream-300 bg-white p-4">
      <summary className="cursor-pointer font-semibold text-leaf-900">Planning an event? Predict likely surplus</summary>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Field label="Planned servings" htmlFor="pl"><input id="pl" type="number" min={1} className={inputCls} value={planned} onChange={(e) => setPlanned(e.target.value)} /></Field>
        <Field label="Expected guests" htmlFor="ex"><input id="ex" type="number" min={1} className={inputCls} value={expected} onChange={(e) => setExpected(e.target.value)} /></Field>
        <Button variant="secondary" type="button" onClick={run}>Predict</Button>
      </div>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}
      {p && (
        <div className="mt-3 rounded-lg border-2 border-dashed border-sky-300 bg-sky-50 p-3 text-sm">
          <div className="font-bold text-sky-900">{p.label}</div>
          <div className="mt-1">Estimated surplus: <strong>{p.predicted_surplus_portions}</strong> portions (likely range {p.range_low}–{p.range_high})</div>
          <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">{p.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          <Button variant="ghost" type="button" className="mt-2 px-0" onClick={() => onUse(p.predicted_surplus_portions)}>Save this prediction with the listing</Button>
          <p className="text-xs text-slate-500">Predictions are estimates only and are never counted as rescued food.</p>
        </div>
      )}
    </details>
  );
}

// ---------------- Create donation ----------------

interface FormState {
  title: string; description: string; food_type: string; food_category: FoodCategory | ""; portions_reported: string;
  prepared_at: string; pickup_deadline: string; storage_condition: Storage | ""; packaging: string; allergens: string;
  pickup_address: string; area: string; latitude: number | null; longitude: number | null;
}

export function CreateDonation() {
  const { me } = useAuth();
  const nav = useNavigate();
  const dp = me?.donor_profile;
  const now = new Date();
  const [f, setF] = useState<FormState>({
    title: "", description: "", food_type: "", food_category: "", portions_reported: "",
    prepared_at: toLocalInput(new Date(now.getTime() - 60 * 60000).toISOString()),
    pickup_deadline: toLocalInput(new Date(now.getTime() + 3 * 3600000).toISOString()),
    storage_condition: "", packaging: "", allergens: "",
    pickup_address: dp?.address ?? "", area: dp?.area ?? "", latitude: dp?.latitude ?? null, longitude: dp?.longitude ?? null,
  });
  const [voice, setVoice] = useState<VoiceResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [image, setImage] = useState<File | null>(null);
  const [prediction, setPrediction] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<PublishResult | null>(null);
  const voiceOn = me?.features.voice_reporting !== false;
  const predictOn = me?.features.surplus_prediction !== false;

  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  const applyVoice = (r: VoiceResult) => {
    setVoice(r);
    setConfirmed(false);
    const d = r.draft;
    setF((cur) => ({
      ...cur,
      title: d.title ?? cur.title,
      food_type: d.food_type ?? cur.food_type,
      food_category: d.food_category ?? cur.food_category,
      portions_reported: d.portions_reported != null ? String(d.portions_reported) : cur.portions_reported,
      prepared_at: d.prepared_at ? toLocalInput(d.prepared_at) : cur.prepared_at,
      pickup_deadline: d.pickup_deadline ? toLocalInput(d.pickup_deadline) : cur.pickup_deadline,
      storage_condition: d.storage_condition ?? cur.storage_condition,
      allergens: d.allergens ?? cur.allergens,
      area: d.area ?? cur.area,
      // Keep the donor's registered exact pin if it is in the same area; otherwise use the area centre.
      latitude: dp && d.area && dp.area === d.area ? dp.latitude : d.latitude ?? cur.latitude,
      longitude: dp && d.area && dp.area === d.area ? dp.longitude : d.longitude ?? cur.longitude,
    }));
  };

  const submit = async (e: FormEvent, publish: boolean) => {
    e.preventDefault();
    setErr(null);
    if (f.latitude == null || f.longitude == null) return setErr("Set the pickup location on the map.");
    if (!f.food_category) return setErr("Choose a food category.");
    if (voice && !confirmed) return setErr("Please confirm that you have reviewed the voice-extracted details.");
    setBusy(true);
    try {
      const body = {
        title: f.title, description: f.description || null, food_type: f.food_type, food_category: f.food_category,
        portions_reported: Number(f.portions_reported), prepared_at: fromLocalInput(f.prepared_at), pickup_deadline: fromLocalInput(f.pickup_deadline),
        storage_condition: f.storage_condition || null, packaging: f.packaging || null, allergens: f.allergens || null,
        pickup_address: f.pickup_address, area: f.area, latitude: f.latitude, longitude: f.longitude,
        source: voice ? "VOICE" : "MANUAL", voice_transcript: voice?.transcript ?? null, voice_language: voice?.language ?? null,
        voice_confirmed: !!voice && confirmed, predicted_surplus_portions: prediction,
      };
      const created = await api.post<ListingDetail>("/api/listings", body);
      if (image) {
        const fd = new FormData();
        fd.append("file", image);
        try {
          await api.upload(`/api/listings/${created.id}/image`, fd);
        } catch (e) {
          setErr(`Listing saved, but the photo upload failed: ${errText(e)}`);
        }
      }
      if (!publish) return nav(`/donations/${created.id}`);
      const pub = await api.post<PublishResult>(`/api/listings/${created.id}/publish`);
      setResult(pub);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const ok = result.safety_result === "ELIGIBLE";
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Notice tone={ok ? "success" : "warning"}>
          <div className="font-semibold">{result.message}</div>
        </Notice>
        {result.issues.length > 0 && (
          <Card title="Safety screening notes">
            <ul className="space-y-1 text-sm">
              {result.issues.map((i) => <li key={i.code}><strong className={i.severity === "BLOCKING" ? "text-chili-700" : "text-turmeric-700"}>{i.severity}</strong> - {i.message}</li>)}
            </ul>
            <p className="mt-2 text-xs text-slate-500">{result.listing.safety_disclaimer}</p>
          </Card>
        )}
        {ok && (
          <Card title={`Matched with ${result.matches_found} verified NGO${result.matches_found === 1 ? "" : "s"}`}>
            {result.listing.matches.length === 0 ? (
              <p className="text-sm text-slate-600">No verified NGO is currently within range and open. We will keep the listing open; you can re-run matching from the donation page.</p>
            ) : (
              <ol className="space-y-2">
                {result.listing.matches.map((m) => (
                  <li key={m.ngo_id} className="rounded-lg border border-cream-300 p-3 text-sm">
                    <div className="flex justify-between font-semibold"><span>#{m.rank} {m.ngo_name}</span><span className="text-leaf-700">{m.score}/100</span></div>
                    <p className="mt-1 text-slate-600">{m.explanation}</p>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        )}
        <Button onClick={() => nav(`/donations/${result.listing.id}`)}>View donation timeline</Button>
      </div>
    );
  }

  return (
    <>
      <PageTitle title="Report surplus food" subtitle="Takes about a minute. Nothing is shared with NGOs until you publish." />
      <div className="space-y-4">
        {voiceOn ? <VoiceReporter onResult={applyVoice} /> : <Notice>Voice reporting is currently turned off by the administrator. Please use the form.</Notice>}
        {voice && (
          <Card title="What we heard">
            {voice.simulated && <div className="mb-3"><SimulatedBanner>{voice.mode}. This sample stands in for a real Sarvam AI transcription.</SimulatedBanner></div>}
            <div className="grid gap-3 text-sm md:grid-cols-2">
              <div><div className="text-xs font-semibold uppercase text-slate-500">Transcript ({LANG_LABEL[voice.language] ?? voice.language})</div><p className="mt-1" lang={voice.language}>{voice.transcript}</p></div>
              {voice.english_text && voice.english_text !== voice.transcript && <div><div className="text-xs font-semibold uppercase text-slate-500">English</div><p className="mt-1">{voice.english_text}</p></div>}
            </div>
            <ul className="mt-3 list-disc pl-5 text-xs text-slate-600">{voice.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            {voice.missing_fields.length > 0 && <div className="mt-3"><Notice tone="warning">Not mentioned - please fill in: {voice.missing_fields.join(", ").replaceAll("_", " ")}</Notice></div>}
            <p className="mt-2 text-xs text-slate-500">Extraction: {voice.extraction_method.replace("_", " ")}. The form below has been pre-filled - check every field.</p>
          </Card>
        )}
        {predictOn && <PredictionPanel onUse={setPrediction} />}
        <form onSubmit={(e) => submit(e, true)}>
          <Card title="Donation details">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Title" htmlFor="title" required><input id="title" required minLength={3} className={inputCls} value={f.title} onChange={set("title")} placeholder="e.g. Wedding dinner surplus" /></Field>
              <Field label="Food items" htmlFor="ft" required><input id="ft" required className={inputCls} value={f.food_type} onChange={set("food_type")} placeholder="rice, sambar, palya..." /></Field>
              <Field label="Food category" htmlFor="cat" required>
                <select id="cat" required className={inputCls} value={f.food_category} onChange={set("food_category")}>
                  <option value="">Select...</option>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field label="Approximate portions" htmlFor="por" required><input id="por" type="number" min={1} required className={inputCls} value={f.portions_reported} onChange={set("portions_reported")} /></Field>
              <Field label="Prepared at (IST)" htmlFor="prep" required><input id="prep" type="datetime-local" required className={inputCls} value={f.prepared_at} onChange={set("prepared_at")} /></Field>
              <Field label="Pickup deadline (IST)" htmlFor="dl" required><input id="dl" type="datetime-local" required className={inputCls} value={f.pickup_deadline} onChange={set("pickup_deadline")} /></Field>
              <Field label="Storage condition" htmlFor="st" hint="Required for safety screening - listings without it are held for admin review.">
                <select id="st" className={inputCls} value={f.storage_condition} onChange={set("storage_condition")}>
                  <option value="">Not specified</option>
                  {Object.entries(STORAGE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field label="Allergens" htmlFor="al" hint="e.g. nuts, dairy, gluten - or 'none'"><input id="al" className={inputCls} value={f.allergens} onChange={set("allergens")} /></Field>
              <Field label="Packaging" htmlFor="pk"><input id="pk" className={inputCls} value={f.packaging} onChange={set("packaging")} placeholder="Steel vessels, foil containers..." /></Field>
              <Field label="Food photo (optional)" htmlFor="img" hint="JPEG, PNG or WebP, max 5 MB">
                <input id="img" type="file" accept="image/jpeg,image/png,image/webp" className="block w-full text-sm" onChange={(e) => setImage(e.target.files?.[0] ?? null)} />
              </Field>
              <div className="md:col-span-2"><Field label="Notes for the NGO" htmlFor="desc"><textarea id="desc" rows={2} className={inputCls} value={f.description} onChange={set("description")} /></Field></div>
              <Field label="Pickup address" htmlFor="pa" required hint="Shared only with the NGO that accepts and its volunteer"><input id="pa" required className={inputCls} value={f.pickup_address} onChange={set("pickup_address")} /></Field>
              <Field label="Area" htmlFor="ar" required><input id="ar" required className={inputCls} value={f.area} onChange={set("area")} /></Field>
              <div className="md:col-span-2">
                <span className="mb-1 block text-sm font-medium text-slate-700">Pickup point <span className="text-chili-600">*</span></span>
                <MapPicker lat={f.latitude} lng={f.longitude} onChange={(lat, lng) => setF((c) => ({ ...c, latitude: lat, longitude: lng }))} />
                <div className="mt-2 grid max-w-md grid-cols-2 gap-2">
                  <input aria-label="Latitude" type="number" step="0.000001" className={inputCls} value={f.latitude ?? ""} onChange={(e) => setF({ ...f, latitude: e.target.value === "" ? null : Number(e.target.value) })} />
                  <input aria-label="Longitude" type="number" step="0.000001" className={inputCls} value={f.longitude ?? ""} onChange={(e) => setF({ ...f, longitude: e.target.value === "" ? null : Number(e.target.value) })} />
                </div>
              </div>
            </div>
            {prediction != null && <p className="mt-3 text-xs text-sky-800">A PREDICTION of {prediction} portions will be saved for reference (not counted as rescued food).</p>}
            {voice && (
              <label className="mt-4 flex items-start gap-2 rounded-lg bg-turmeric-100/60 p-3 text-sm">
                <input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                <span>I have checked the details extracted from my voice report and they are correct.</span>
              </label>
            )}
            <p className="mt-4 text-xs text-slate-500">
              Publishing runs automatic safety screening and matches only administrator-verified NGOs. FestivePlate does not certify food as safe; please follow FSSAI food-handling guidelines.
            </p>
            {err && <div className="mt-3"><ErrorBox message={err} /></div>}
            <div className="mt-4 flex flex-wrap gap-3">
              <Button type="submit" busy={busy}>Publish and find NGOs</Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={(e) => submit(e as unknown as FormEvent, false)}>Save as draft</Button>
            </div>
          </Card>
        </form>
      </div>
    </>
  );
}
