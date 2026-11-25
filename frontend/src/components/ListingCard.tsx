import { Link } from "react-router-dom";
import type { Listing } from "../types";
import { CATEGORY_LABEL, fmtDateTime, STORAGE_LABEL, timeLeft } from "../utils";
import { cx, DemoBadge, StatusBadge } from "./ui";

const OPEN = ["DRAFT", "PUBLISHED", "MATCHED", "ACCEPTED", "PICKUP_ASSIGNED", "PICKED_UP"];

export function ListingCard({ l, extra, to }: { l: Listing; extra?: React.ReactNode; to?: string }) {
  const left = timeLeft(l.pickup_deadline);
  const urgent = OPEN.includes(l.status) && left.minutes > 0 && left.minutes < 90;
  return (
    <article className="rounded-xl border border-cream-300 bg-white p-4 shadow-sm transition hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link to={to ?? `/donations/${l.id}`} className="font-semibold text-leaf-900 hover:underline">
            {l.title}
          </Link>
          <div className="mt-0.5 text-sm text-slate-600">{l.food_type}</div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {l.is_demo && <DemoBadge />}
          {l.emergency && <span className="rounded-full bg-chili-600 px-2 py-0.5 text-xs font-bold text-white">Urgent</span>}
          <StatusBadge status={l.status} />
        </div>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-slate-500">Portions</dt><dd className="font-semibold">{l.portions_reported}</dd></div>
        <div><dt className="text-xs text-slate-500">Type</dt><dd>{CATEGORY_LABEL[l.food_category]}</dd></div>
        <div><dt className="text-xs text-slate-500">Area</dt><dd>{l.area}</dd></div>
        <div>
          <dt className="text-xs text-slate-500">Pickup by</dt>
          <dd className={cx(urgent && "font-semibold text-chili-700")}>
            {fmtDateTime(l.pickup_deadline)}
            {OPEN.includes(l.status) && <span className="block text-xs">{left.label}</span>}
          </dd>
        </div>
      </dl>
      {l.storage_condition && <div className="mt-2 text-xs text-slate-500">Storage: {STORAGE_LABEL[l.storage_condition]}{l.allergens ? ` · Allergens: ${l.allergens}` : ""}</div>}
      {extra && <div className="mt-3">{extra}</div>}
    </article>
  );
}
