import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** All times displayed in India Standard Time - the platform operates in Bengaluru. */
const IST = "Asia/Kolkata";

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-IN", { timeZone: IST, day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: IST, hour: "numeric", minute: "2-digit" });
}

export function timeLeft(iso: string): { label: string; minutes: number } {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (minutes <= 0) return { label: "deadline passed", minutes };
  if (minutes < 60) return { label: `${minutes} min left`, minutes };
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return { label: `${h} h ${m ? `${m} min ` : ""}left`, minutes };
}

/** Convert ISO (UTC) to the value expected by <input type="datetime-local"> in IST. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const ist = new Date(d.getTime() + 330 * 60000);
  return ist.toISOString().slice(0, 16);
}

/** Interpret a datetime-local value as IST and return UTC ISO. */
export function fromLocalInput(v: string): string {
  return new Date(`${v}:00+05:30`).toISOString();
}

export const STATUS_STYLE: Record<string, string> = {
  DRAFT: "bg-slate-100 text-slate-700 ring-slate-300",
  PUBLISHED: "bg-sky-50 text-sky-800 ring-sky-300",
  MATCHED: "bg-indigo-50 text-indigo-800 ring-indigo-300",
  ACCEPTED: "bg-leaf-50 text-leaf-800 ring-leaf-300",
  PICKUP_ASSIGNED: "bg-teal-50 text-teal-800 ring-teal-300",
  PICKED_UP: "bg-turmeric-100 text-turmeric-700 ring-turmeric-500",
  DELIVERED: "bg-leaf-600 text-white ring-leaf-700",
  CANCELLED: "bg-slate-200 text-slate-600 ring-slate-400",
  EXPIRED: "bg-slate-200 text-slate-600 ring-slate-400",
  FLAGGED: "bg-chili-100 text-chili-700 ring-chili-600",
};

export const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft", PUBLISHED: "Published", MATCHED: "Matched", ACCEPTED: "Accepted", PICKUP_ASSIGNED: "Pickup assigned",
  PICKED_UP: "Picked up", DELIVERED: "Delivered", CANCELLED: "Cancelled", EXPIRED: "Expired", FLAGGED: "Flagged for review",
};

export const CATEGORY_LABEL: Record<string, string> = { VEG: "Vegetarian", NON_VEG: "Non-vegetarian", EGG: "Contains egg", MIXED: "Mixed veg / non-veg" };
export const STORAGE_LABEL: Record<string, string> = {
  HOT_HELD: "Kept hot (hot-held)", REFRIGERATED: "Refrigerated", ROOM_TEMPERATURE: "Room temperature", FROZEN: "Frozen",
};
export const LANG_LABEL: Record<string, string> = { en: "English", kn: "ಕನ್ನಡ Kannada", hi: "हिन्दी Hindi" };

export function mapsDirections(lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

export function errText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}

/** Small data-loading hook with loading / error / reload. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    if (!pollMs) return;
    const t = setInterval(() => reload(true), pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}
