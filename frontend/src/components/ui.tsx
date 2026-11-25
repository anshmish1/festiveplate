import { ButtonHTMLAttributes, ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { STATUS_LABEL, STATUS_STYLE } from "../utils";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", STATUS_STYLE[status] ?? STATUS_STYLE.DRAFT)}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function DemoBadge({ label = "DEMO" }: { label?: string }) {
  return (
    <span className="inline-flex items-center rounded border border-dashed border-turmeric-500 bg-turmeric-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-turmeric-700" title="Demonstration data - not a real organisation or event">
      {label}
    </span>
  );
}

export function SimulatedBanner({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="rounded-lg border-2 border-dashed border-turmeric-500 bg-turmeric-100/60 p-3 text-sm text-turmeric-700">
      <span className="mr-2 font-bold">SIMULATED / DEMO:</span>
      {children}
    </div>
  );
}

type Variant = "primary" | "secondary" | "danger" | "ghost";
export function Button({ variant = "primary", className, busy, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-leaf-600 text-white hover:bg-leaf-700 focus-visible:outline-leaf-700",
    secondary: "bg-white text-leaf-800 ring-1 ring-inset ring-leaf-300 hover:bg-leaf-50 focus-visible:outline-leaf-600",
    danger: "bg-chili-600 text-white hover:bg-chili-700 focus-visible:outline-chili-700",
    ghost: "text-leaf-800 hover:bg-leaf-50 focus-visible:outline-leaf-600",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold shadow-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
    >
      {busy && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-cream-300 bg-white p-5 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-lg font-semibold text-leaf-900">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-cream-300 bg-white p-4 shadow-sm">
      <div className="text-sm text-slate-600">{label}</div>
      <div className="mt-1 text-2xl font-bold text-leaf-800">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 p-6 text-slate-600">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-leaf-500 border-t-transparent" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-chili-600/40 bg-chili-100 p-3 text-sm text-chili-700">
      <span>{message}</span>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-cream-300 bg-cream-50 p-8 text-center">
      <div className="text-base font-semibold text-slate-700">{title}</div>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function Field({ label, htmlFor, hint, error, children, required }: { label: string; htmlFor: string; hint?: string; error?: string; children: ReactNode; required?: boolean }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">
        {label} {required && <span className="text-chili-600" aria-hidden>*</span>}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && <p className="mt-1 text-xs font-medium text-chili-700">{error}</p>}
    </div>
  );
}

export const inputCls =
  "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-leaf-500 focus:outline-none focus:ring-2 focus:ring-leaf-200 disabled:bg-slate-100";

export function Notice({ tone = "info", children }: { tone?: "info" | "success" | "warning" | "error"; children: ReactNode }) {
  const t = {
    info: "border-sky-300 bg-sky-50 text-sky-900",
    success: "border-leaf-300 bg-leaf-50 text-leaf-900",
    warning: "border-turmeric-500 bg-turmeric-100 text-turmeric-700",
    error: "border-chili-600/40 bg-chili-100 text-chili-700",
  }[tone];
  return <div role={tone === "error" ? "alert" : "status"} className={cx("rounded-lg border p-3 text-sm", t)}>{children}</div>;
}

/** Fetches a protected image with the user's token and renders it as a blob URL. */
export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoke: string | null = null;
    let alive = true;
    api.blob(path).then(
      (b) => {
        if (!alive) return;
        revoke = URL.createObjectURL(b);
        setUrl(revoke);
      },
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [path]);
  if (failed) return <div className="text-xs text-slate-500">Image unavailable</div>;
  if (!url) return <div className={cx("animate-pulse bg-cream-200", className)} aria-label="Loading image" />;
  return <img src={url} alt={alt} className={className} />;
}

export function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="w-28 shrink-0 text-slate-600">{label}</div>
      <div className="h-4 flex-1 overflow-hidden rounded bg-cream-200" role="img" aria-label={`${label}: ${value}`}>
        <div className="h-full rounded bg-leaf-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-14 text-right font-semibold text-leaf-800">{value}</div>
    </div>
  );
}
