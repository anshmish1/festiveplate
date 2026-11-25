// Thin fetch wrapper. All AI/integration credentials live on the backend only;
// the browser only ever holds the user's own short-lived JWT.

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const TOKEN_KEY = "fp_token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((e: { loc?: unknown[]; msg?: string }) => {
          const field = (e.loc ?? []).filter((x) => x !== "body").join(".");
          return field ? `${field}: ${e.msg}` : e.msg;
        })
        .join("; ");
    }
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the FestivePlate server. Check your connection and try again.");
  }
  if (res.status === 401 && token) onUnauthorized?.();
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, errorMessage(parsed, `Request failed (${res.status})`));
  }
  if (raw) return (await res.blob()) as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {}),
  patch: <T>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {}),
  del: <T>(p: string) => request<T>("DELETE", p),
  upload: <T>(p: string, form: FormData) => request<T>("POST", p, form),
  blob: (p: string) => request<Blob>("GET", p, undefined, true),
};
