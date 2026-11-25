import { ReactNode, useState } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { homeFor, useAuth } from "../auth";
import type { Notification, Role } from "../types";
import { fmtDateTime, useLoad } from "../utils";
import { cx, DemoBadge } from "./ui";

const NAV: Record<Role, { to: string; label: string }[]> = {
  DONOR: [
    { to: "/donor", label: "My donations" },
    { to: "/donor/new", label: "Report surplus" },
    { to: "/impact", label: "Impact" },
  ],
  NGO: [
    { to: "/ngo", label: "Available food" },
    { to: "/impact", label: "Impact" },
  ],
  VOLUNTEER: [{ to: "/volunteer", label: "My pickups" }],
  ADMIN: [
    { to: "/admin", label: "Admin" },
    { to: "/admin/system", label: "System health" },
    { to: "/impact", label: "Impact" },
  ],
};

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-bold text-leaf-800">
      <img src="/favicon.svg" alt="" className="h-8 w-8" />
      <span className="text-lg">FestivePlate</span>
    </Link>
  );
}

function Bell() {
  const [open, setOpen] = useState(false);
  const { data, reload } = useLoad(() => api.get<Notification[]>("/api/me/notifications"), [], 20000);
  const unread = (data ?? []).filter((n) => !n.read_at).length;
  const markAll = async () => {
    await api.post("/api/me/notifications/read-all");
    reload(true);
  };
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-full p-2 text-leaf-800 hover:bg-leaf-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-leaf-600"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" /></svg>
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-chili-600 px-1.5 text-[10px] font-bold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-[1000] mt-2 w-80 max-w-[90vw] rounded-xl border border-cream-300 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-cream-200 px-4 py-2">
            <span className="font-semibold">Notifications</span>
            {unread > 0 && <button onClick={markAll} className="text-xs font-medium text-leaf-700 hover:underline">Mark all read</button>}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {(data ?? []).length === 0 && <li className="p-4 text-sm text-slate-500">No notifications yet.</li>}
            {(data ?? []).slice(0, 30).map((n) => (
              <li key={n.id} className={cx("border-b border-cream-100 px-4 py-3 text-sm", !n.read_at && "bg-leaf-50/60")}>
                {n.listing_id ? (
                  <Link to={`/donations/${n.listing_id}`} onClick={() => setOpen(false)} className="font-medium text-leaf-800 hover:underline">{n.title}</Link>
                ) : (
                  <span className="font-medium">{n.title}</span>
                )}
                <p className="mt-0.5 text-slate-600">{n.body}</p>
                <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-400">
                  <span>{fmtDateTime(n.created_at)}</span>
                  {n.channel === "SMS_SIMULATED" && <DemoBadge label="SMS simulated" />}
                  {n.status === "FAILED" && <span className="text-chili-700">Translation failed - shown in English</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const items = me ? NAV[me.user.role] : [];
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[2000] focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <header className="sticky top-0 z-[900] border-b border-cream-300 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <Logo />
          <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
            {items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end
                className={({ isActive }) => cx("rounded-lg px-3 py-1.5 text-sm font-medium", isActive ? "bg-leaf-100 text-leaf-900" : "text-slate-700 hover:bg-cream-100")}
              >
                {i.label}
              </NavLink>
            ))}
          </nav>
          {me ? (
            <div className="flex items-center gap-2">
              <Bell />
              <NavLink to="/settings" className="hidden text-sm text-slate-700 hover:underline sm:block" title="Settings">
                {me.user.full_name}
              </NavLink>
              <NavLink to="/settings" className="rounded-lg px-2 py-1 text-sm text-slate-700 hover:bg-cream-100 sm:hidden">Settings</NavLink>
              <button onClick={() => { logout(); nav("/"); }} className="rounded-lg px-3 py-1.5 text-sm font-medium text-leaf-800 hover:bg-leaf-50">Log out</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Link to="/login" className="rounded-lg px-3 py-1.5 text-sm font-medium text-leaf-800 hover:bg-leaf-50">Log in</Link>
              <Link to="/register" className="rounded-lg bg-leaf-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-leaf-700">Join</Link>
            </div>
          )}
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 pt-4 text-xs text-slate-500">
        FestivePlate connects surplus food with verified NGOs. It does not certify food as safe to eat - donors and receiving organisations remain responsible for food-safety checks.
        Entries marked <DemoBadge /> are demonstration data.
      </footer>
    </div>
  );
}

export function RequireRole({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null;
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (roles && !roles.includes(me.user.role)) return <Navigate to={homeFor(me.user.role)} replace />;
  return <>{children}</>;
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-leaf-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
