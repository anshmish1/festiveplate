import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { homeFor, useAuth } from "../auth";
import { MapPicker } from "../components/Maps";
import { Button, Card, DemoBadge, ErrorBox, Field, inputCls } from "../components/ui";
import type { Role } from "../types";
import { errText, useLoad } from "../utils";

const DEMO_ACCOUNTS: { role: string; email: string; note: string }[] = [
  { role: "Donor", email: "shubha.mantapa@festiveplate.demo", note: "Electronic City wedding hall (Kannada)" },
  { role: "NGO", email: "hasiru@festiveplate.demo", note: "Verified, has vehicle" },
  { role: "NGO", email: "annapoorna@festiveplate.demo", note: "Verified, veg only" },
  { role: "NGO", email: "kmc@festiveplate.demo", note: "Pending verification" },
  { role: "Volunteer", email: "ravi.volunteer@festiveplate.demo", note: "Hasiru Food Bank" },
  { role: "Admin", email: "admin@festiveplate.demo", note: "Platform admin" },
];

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const u = await login(email, password);
      nav(loc.state?.from ?? homeFor(u.role), { replace: true });
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto grid max-w-4xl gap-6 md:grid-cols-2">
      <Card title="Log in">
        <form onSubmit={submit} className="space-y-4" noValidate>
          <Field label="Email" htmlFor="email" required>
            <input id="email" type="email" autoComplete="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password" htmlFor="password" required>
            <input id="password" type="password" autoComplete="current-password" required className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {err && <ErrorBox message={err} />}
          <Button type="submit" busy={busy} className="w-full">Log in</Button>
          <p className="text-center text-sm text-slate-600">New here? <Link to="/register" className="font-medium text-leaf-700 hover:underline">Create an account</Link></p>
        </form>
      </Card>
      <Card title={<span className="flex items-center gap-2">Demo accounts <DemoBadge /></span>}>
        <p className="mb-3 text-sm text-slate-600">
          All demo accounts use the password shown in the README (default <code className="rounded bg-cream-100 px-1">Demo@12345</code>). Click to fill in.
        </p>
        <ul className="space-y-2">
          {DEMO_ACCOUNTS.map((a) => (
            <li key={a.email}>
              <button
                type="button"
                onClick={() => { setEmail(a.email); setPassword("Demo@12345"); }}
                className="w-full rounded-lg border border-cream-300 px-3 py-2 text-left text-sm hover:bg-leaf-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-leaf-600"
              >
                <span className="font-semibold text-leaf-800">{a.role}</span> · {a.email}
                <span className="block text-xs text-slate-500">{a.note}</span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

const DONOR_TYPES = ["WEDDING_HALL", "RESTAURANT", "HOTEL", "CATERER", "EVENT_ORGANIZER", "HOUSEHOLD", "OTHER"];

export function Register() {
  const { acceptToken } = useAuth();
  const nav = useNavigate();
  const [role, setRole] = useState<Exclude<Role, "ADMIN">>("DONOR");
  const [f, setF] = useState({
    email: "", password: "", full_name: "", phone: "", preferred_language: "en",
    organization_name: "", donor_type: "WEDDING_HALL", registration_number: "", contact_person: "",
    address: "", area: "", service_radius_km: "10", daily_capacity_portions: "200", accepts_veg: true, accepts_non_veg: true,
    has_vehicle: false, ngo_id: "", vehicle_type: "",
  });
  const [pos, setPos] = useState<{ lat: number | null; lng: number | null }>({ lat: null, lng: null });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ngos = useLoad(() => api.get<{ id: number; organization_name: string; area: string }[]>("/api/auth/verified-ngos"));
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if ((role === "DONOR" || role === "NGO") && (pos.lat == null || pos.lng == null)) {
      setErr("Please set your location on the map.");
      return;
    }
    const body: Record<string, unknown> = {
      email: f.email, password: f.password, full_name: f.full_name, phone: f.phone || null, role, preferred_language: f.preferred_language,
    };
    if (role === "DONOR")
      body.donor = { organization_name: f.organization_name, donor_type: f.donor_type, address: f.address, area: f.area, latitude: pos.lat, longitude: pos.lng };
    if (role === "NGO")
      body.ngo = {
        organization_name: f.organization_name, registration_number: f.registration_number, contact_person: f.contact_person || f.full_name,
        address: f.address, area: f.area, latitude: pos.lat, longitude: pos.lng, service_radius_km: Number(f.service_radius_km),
        daily_capacity_portions: Number(f.daily_capacity_portions), accepts_veg: f.accepts_veg, accepts_non_veg: f.accepts_non_veg, has_vehicle: f.has_vehicle,
      };
    if (role === "VOLUNTEER") body.volunteer = { ngo_id: Number(f.ngo_id), vehicle_type: f.vehicle_type || null, area: f.area || null };
    setBusy(true);
    try {
      const r = await api.post<{ access_token: string }>("/api/auth/register", body);
      const u = await acceptToken(r.access_token);
      nav(homeFor(u.role), { replace: true });
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <Card title="Create your account">
        <form onSubmit={submit} className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-slate-700">I am a...</legend>
            <div className="grid grid-cols-3 gap-2">
              {(["DONOR", "NGO", "VOLUNTEER"] as const).map((r) => (
                <label key={r} className={`cursor-pointer rounded-lg border px-3 py-2 text-center text-sm font-medium ${role === r ? "border-leaf-500 bg-leaf-50 text-leaf-900" : "border-slate-300"}`}>
                  <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} className="sr-only" />
                  {r === "DONOR" ? "Food donor" : r === "NGO" ? "NGO / shelter" : "Volunteer"}
                </label>
              ))}
            </div>
            {role === "NGO" && <p className="mt-2 text-xs text-slate-500">NGO accounts must be verified by a FestivePlate administrator before they can see or accept donations.</p>}
          </fieldset>

          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Full name" htmlFor="full_name" required><input id="full_name" required className={inputCls} value={f.full_name} onChange={set("full_name")} /></Field>
            <Field label="Phone" htmlFor="phone" hint="Shared only with the organisation handling your donation"><input id="phone" type="tel" className={inputCls} value={f.phone} onChange={set("phone")} placeholder="+91 98xxx xxxxx" /></Field>
            <Field label="Email" htmlFor="remail" required><input id="remail" type="email" autoComplete="email" required className={inputCls} value={f.email} onChange={set("email")} /></Field>
            <Field label="Password" htmlFor="rpassword" required hint="At least 8 characters with a letter and a number"><input id="rpassword" type="password" autoComplete="new-password" required minLength={8} className={inputCls} value={f.password} onChange={set("password")} /></Field>
            <Field label="Preferred language" htmlFor="lang">
              <select id="lang" className={inputCls} value={f.preferred_language} onChange={set("preferred_language")}>
                <option value="en">English</option><option value="kn">ಕನ್ನಡ (Kannada)</option><option value="hi">हिन्दी (Hindi)</option>
              </select>
            </Field>
          </div>

          {(role === "DONOR" || role === "NGO") && (
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Organisation name" htmlFor="org" required><input id="org" required className={inputCls} value={f.organization_name} onChange={set("organization_name")} /></Field>
              {role === "DONOR" ? (
                <Field label="Donor type" htmlFor="dtype">
                  <select id="dtype" className={inputCls} value={f.donor_type} onChange={set("donor_type")}>
                    {DONOR_TYPES.map((d) => <option key={d} value={d}>{d.replace("_", " ").toLowerCase()}</option>)}
                  </select>
                </Field>
              ) : (
                <Field label="Registration number" htmlFor="reg" required><input id="reg" required className={inputCls} value={f.registration_number} onChange={set("registration_number")} /></Field>
              )}
              <Field label="Address" htmlFor="addr" required><input id="addr" required className={inputCls} value={f.address} onChange={set("address")} /></Field>
              <Field label="Area / locality" htmlFor="area" required><input id="area" required className={inputCls} value={f.area} onChange={set("area")} placeholder="e.g. Electronic City" /></Field>
              {role === "NGO" && (
                <>
                  <Field label="Contact person" htmlFor="cp"><input id="cp" className={inputCls} value={f.contact_person} onChange={set("contact_person")} /></Field>
                  <Field label="Service radius (km)" htmlFor="rad"><input id="rad" type="number" min={1} max={100} className={inputCls} value={f.service_radius_km} onChange={set("service_radius_km")} /></Field>
                  <Field label="Daily capacity (portions)" htmlFor="cap"><input id="cap" type="number" min={1} className={inputCls} value={f.daily_capacity_portions} onChange={set("daily_capacity_portions")} /></Field>
                  <div className="flex flex-wrap items-center gap-4 pt-6 text-sm">
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.accepts_veg} onChange={set("accepts_veg")} /> Accepts veg</label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.accepts_non_veg} onChange={set("accepts_non_veg")} /> Accepts non-veg</label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.has_vehicle} onChange={set("has_vehicle")} /> Has vehicle</label>
                  </div>
                </>
              )}
              <div className="md:col-span-2">
                <span className="mb-1 block text-sm font-medium text-slate-700">Location <span className="text-chili-600">*</span></span>
                <MapPicker lat={pos.lat} lng={pos.lng} onChange={(lat, lng) => setPos({ lat, lng })} />
                <p className="mt-1 text-xs text-slate-500">{pos.lat != null ? `Pin at ${pos.lat.toFixed(5)}, ${pos.lng!.toFixed(5)}` : "Click the map to place your pin."}</p>
              </div>
            </div>
          )}

          {role === "VOLUNTEER" && (
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Volunteer with NGO" htmlFor="ngo" required>
                <select id="ngo" required className={inputCls} value={f.ngo_id} onChange={set("ngo_id")}>
                  <option value="">Select a verified NGO</option>
                  {(ngos.data ?? []).map((n) => <option key={n.id} value={n.id}>{n.organization_name} - {n.area}</option>)}
                </select>
              </Field>
              <Field label="Vehicle" htmlFor="veh"><input id="veh" className={inputCls} value={f.vehicle_type} onChange={set("vehicle_type")} placeholder="Two-wheeler, car, van..." /></Field>
              <Field label="Area" htmlFor="varea"><input id="varea" className={inputCls} value={f.area} onChange={set("area")} /></Field>
            </div>
          )}

          {err && <ErrorBox message={err} />}
          <Button type="submit" busy={busy}>Create account</Button>
        </form>
      </Card>
    </div>
  );
}
