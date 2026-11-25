# FestivePlate

**Rescue surplus food from Bengaluru's weddings, festivals, restaurants and caterers, and get it to verified NGOs before it spoils.**

FestivePlate is a food surplus prediction, rescue and redistribution platform. Donors report surplus food by form or by voice (Kannada, Hindi or English). The platform screens it for safety risks and matches it to nearby **verified** NGOs, with an explanation for every match. Volunteers then pick it up and confirm delivery. Impact numbers count **only confirmed deliveries**.

> **Status:** working MVP. The app runs end to end with **no external credentials**. Any integration without credentials runs in a clearly labelled DEMO or NOT CONFIGURED mode, and the app never claims a live connection it doesn't have. All seeded organisations and people are fictional and marked "(DEMO)".

---

## Contents

- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Demo walkthrough](#demo-walkthrough)
- [Architecture](#architecture)
- [Donation lifecycle](#donation-lifecycle)
- [Integrations and credentials](#integrations-and-credentials)
- [Safety, privacy and security](#safety-privacy-and-security)
- [Testing](#testing)
- [API](#api)
- [Deployment notes](#deployment-notes)
- [Known limitations](#known-limitations)

---

## Quick start (Docker)

```bash
cp .env.example .env          # optional: everything works with defaults
docker compose up --build
```

Open **http://localhost:8080**. On start-up the backend applies Alembic migrations and seeds demo data. Seeding is idempotent; set `SEED_DEMO_DATA=false` to skip it.

| Service  | Port | Notes |
|----------|------|-------|
| frontend | 8080 | nginx serving the React build; proxies `/api`, `/health`, `/metrics`, `/docs` |
| backend  | internal 8000 | FastAPI |
| db       | internal 5432 | PostgreSQL 16, volume `pgdata` |

## Local development

Requirements: Python 3.11+, Node 20+. PostgreSQL 16 is recommended; SQLite works for quick runs.

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Option A - PostgreSQL
export DATABASE_URL=postgresql://localhost:5432/festiveplate
alembic upgrade head
python -m app.seed

# Option B - SQLite, zero setup
python -m app.seed --create-tables

uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000
```

To point the dev proxy at a different backend, set `VITE_PROXY_TARGET`. For a build served from a different origin than the API, set `VITE_API_BASE`.

## Demo walkthrough

Every demo account uses the password **`Demo@12345`**. The login page also has one-click quick-fill buttons for them.

| Role | Email | Who |
|------|-------|-----|
| Admin | `admin@festiveplate.demo` | Platform administrator |
| Donor | `shubha.mantapa@festiveplate.demo` | Shubha Kalyana Mantapa (wedding hall, Electronic City) |
| Donor | `udupi.grand@festiveplate.demo` | Udupi Grand Restaurant (Koramangala) |
| Donor | `hsr.caterers@festiveplate.demo` | HSR Feast Caterers (HSR Layout) |
| NGO | `annapoorna@festiveplate.demo` | Annapoorna Community Kitchen (Begur), verified |
| NGO | `hasiru@festiveplate.demo` | Hasiru Food Bank (Bommanahalli), verified |
| NGO | `nammaoota@festiveplate.demo` | Namma Oota Seva Trust (HSR Layout), verified |
| NGO | `yelahanka@festiveplate.demo`, `jayanagar@festiveplate.demo` | verified, far from the south-east donors |
| NGO | `kmc@festiveplate.demo` | Koramangala Meals Collective, **pending verification** |
| Volunteer | `ravi.volunteer@festiveplate.demo`, `priya.volunteer@festiveplate.demo` | Hasiru Food Bank |
| Volunteer | `lakshmi.volunteer@festiveplate.demo` | Annapoorna |
| Volunteer | `arjun.volunteer@festiveplate.demo` | Namma Oota |

**A 10-minute end-to-end run.** Use separate browser profiles or a private window per role; sessions live in `sessionStorage`, so each tab has its own login.

1. **Donor: report surplus.** Log in as `shubha.mantapa`, then go to **New donation**.
   - *Voice:* choose a language and click **Use DEMO sample report**. A sample report is extracted into the form, marked **DEMO - sample input, Sarvam AI not called**. Review the fields and tick the confirmation box. With `SARVAM_API_KEY` set you can record real audio instead (up to 60 s).
   - Alternatively, fill the form by hand: set the pickup point on the map and add an optional photo.
   - Click **Publish and find NGOs**. The safety screen runs, and matching ranks verified NGOs within reach. Each match shows its score and a plain-language reason, for example: "4.2 km away, has capacity for 120 portions today, can reach you about 25 min before the deadline".
2. **NGO: accept.** Log in as `hasiru` (or `annapoorna`). The donation appears under **Available donations matched to you**; until acceptance, it shows only an approximate location. Open it and click **Accept donation**. Acceptance is atomic: if two NGOs click at the same moment, exactly one wins and the other gets a clear "already accepted" message.
3. **NGO: assign a volunteer.** On the same page, pick `Ravi Kumar (DEMO)` and click **Assign**.
4. **Volunteer: pick up.** Log in as `ravi.volunteer`. **My pickups** shows the donation, directions to the pickup and to the NGO, and the donor's contact details. Click **Confirm pickup** and enter the portions actually collected (for example 110 of 120 reported).
5. **Volunteer: deliver.** Click **Confirm delivery** and enter the portions delivered (no more than the number collected).
6. **NGO: acknowledge.** Log back in as the NGO and click **Acknowledge receipt of food**. The digital receipt becomes available only now.
7. **Impact.** Open **Impact**: delivered, collected and reported portions are shown separately, and the new delivery is counted.
8. **Admin.** Log in as `admin`:
   - **NGO verification:** verify or reject Koramangala Meals Collective. Pending NGOs never receive matches.
   - **Safety flags:** the seeded "Sweets and snacks from a naming ceremony" donation is flagged (storage condition missing, so an admin must review it). Open it, then clear or reject it.
   - **Feature flags:** turn `voice_reporting` off (with a reason) and confirm the donor's voice panel disappears. Every change is recorded in the audit history.
   - **System health:** request and error metrics, Sarvam/Flagsmith/NudgeBee status (NudgeBee shows **NOT CONFIGURED**), incidents and failed notifications. The AI SRE insight cards sit under a **SIMULATED** banner.

## Architecture

```
React + TS + Tailwind (Vite) --REST/JSON--> FastAPI --SQLAlchemy--> PostgreSQL
                                                |
                                                +- Sarvam AI (STT, translate, extraction)  [server-side only]
                                                +- Flagsmith (feature flags)               [server-side only]
                                                +- /metrics + structured logs -> NudgeBee / Prometheus
```

```
backend/
  app/
    main.py            app factory, middleware (request metrics, security headers, errors)
    config.py          pydantic-settings; all env vars
    models.py          16 tables; enums enforced with CHECK constraints
    schemas.py         request/response models (UTC timestamps serialised with "Z")
    security.py        bcrypt passwords, JWT
    deps.py            auth + role guards
    ratelimit.py       per-IP sliding-window limits (auth, AI, default)
    services/          matching, safety, state machine, extraction, prediction,
                       sarvam, flags, notifications, monitoring, impact, storage, timegeo
    routers/           auth, me, listings, ngo, volunteer, ai, admin, impact, public
    seed.py            Bengaluru demo data
  alembic/             migrations (0001_initial_schema)
  tests/               pytest: unit rules, full donation flow, concurrency, expiry, platform
frontend/src/
  pages/               Landing, Auth, Donor, DonationDetail, Ngo, Volunteer, Admin, Misc (Impact, System health, Settings)
  components/          Layout/nav, UI kit, Leaflet maps, listing card
docs/openapi.json      exported OpenAPI 3 spec
```

### Matching

Only NGOs that are **verified**, active, accept the food type (veg or non-veg), are within their own service radius, and have capacity left today are considered. Each candidate is scored out of 100:

| Factor | Weight |
|--------|--------|
| Distance | 35 |
| Remaining daily capacity vs portions | 20 |
| Can reach the donor before the pickup deadline (estimated travel time) | 20 |
| Pickup hours overlap the window | 10 |
| Food preference fit | 10 |
| Vehicle available for large donations | 5 |

Every match stores a human-readable explanation. If no NGO qualifies, the donor is told so ("No verified NGO currently meets the criteria") and the donation stays published for later matching; NGOs are never invented. When the `emergency_matching` flag is on and the deadline is less than 2 hours away, the radius is widened and urgent notifications are sent.

### Surplus prediction

`POST /api/ai/predict` estimates likely surplus from event type, guest count, menu size and festival or season factors, using a transparent heuristic. Results are labelled *estimates*, come with a confidence range, and are never added to impact totals.

## Donation lifecycle

```
DRAFT -> PUBLISHED -> MATCHED -> ACCEPTED -> PICKUP_ASSIGNED -> PICKED_UP -> DELIVERED
  |          |           |          |              |
  +----------+-----------+----------+--------------+--> CANCELLED / EXPIRED
  FLAGGED (safety review) -> cleared -> PUBLISHED/MATCHED  |  rejected -> CANCELLED
```

- All transitions go through a single state machine (`services/state.py`) and are written to `donation_status_history`, which feeds the timeline on each donation's page.
- Acceptance is a conditional `UPDATE ... WHERE status='MATCHED'` checked by row count. Partial unique indexes guarantee at most one accepted NGO and one active volunteer assignment per donation. The tests cover this under real concurrency on both SQLite and PostgreSQL.
- Donations past their pickup deadline expire automatically. A flagged donation edited by the donor goes back to DRAFT and is screened again on publish.
- **Reported**, **collected** and **delivered** portions are stored separately. Delivered can never exceed collected. Receipts and impact count only after delivery is confirmed.

## Integrations and credentials

All keys are read **only by the backend**. The frontend never receives them; it asks the backend for a status such as `configured: true/false`.

| Integration | Env vars | Without credentials | With credentials |
|---|---|---|---|
| **Sarvam AI** | `SARVAM_API_KEY` (+ optional model names) | Voice demo returns a sample report labelled **DEMO - Sarvam AI not called**. Uploading real audio returns a clear 503 "not configured". Notifications are sent in English. Text extraction uses the built-in rule-based extractor. | Speech-to-text (`saarika`), translation of notifications into kn/hi (`mayura`), LLM-assisted extraction (`sarvam-m`) with rule-based fallback. Failures are recorded as incidents and failed notifications can be retried from System health. |
| **Flagsmith** | `FLAGSMITH_ENVIRONMENT_KEY`, `FLAGSMITH_API_URL` | Safe defaults: `voice_reporting` on, `surplus_prediction` on, `emergency_matching` off, `multilingual_notifications` on, `impact_dashboard` on. Admin overrides still work. | Flags are fetched server-side and cached for 60 s. Resolution order: admin override → Flagsmith → default. The admin screen shows where each value came from. |
| **NudgeBee** | `NUDGEBEE_ENABLED`, `NUDGEBEE_WEBHOOK_URL`, `NUDGEBEE_API_KEY` | System health shows **NOT CONFIGURED** and `live: false`. Example AI SRE insights are shown only under a SIMULATED banner. | The app exposes signals for NudgeBee to ingest: Prometheus `/metrics` (protect with `METRICS_TOKEN`), structured JSON logs, `/health`, and incident records. No live NudgeBee API connection is implemented or claimed; see limitations. |
| **SMS** | none | Simulated: SMS notifications are logged, never sent, and labelled in Settings. | Not implemented. |
| **Maps** | none | OpenStreetMap tiles via Leaflet; directions links open Google Maps. | n/a |

## Safety, privacy and security

- **Food safety.** The rule-based screen checks hold time since preparation against storage condition, high-risk food at room temperature, undeclared allergens, missing storage information and deadlines that have passed. It **never certifies food as safe**: every result carries the disclaimer "Automated screening only - FestivePlate does not certify food as safe", and the receiving NGO must inspect the food. Blocking issues (for example missing storage info, an unsafe hold time or a past deadline) send the donation to admin review; warnings are shown to the NGO.
- **Privacy.** Until an NGO accepts a donation, other NGOs see only the area and coordinates rounded to about 1 km. The exact address, donor name, phone number and voice transcript are hidden. Unrelated users get a 404, not a 403.
- **Auth.** bcrypt password hashes and short-lived JWTs (HS256; `JWT_SECRET` is required when `APP_ENV=production`). Role guards apply on every route. NGO accounts are inactive for matching until an admin verifies them. Deactivated users are rejected immediately.
- **Input handling.** Pydantic validation on every request. Uploads are size-limited, and image type is checked by magic bytes and stored under random names. Protected images are served only through authorised endpoints.
- **Abuse controls.** Per-IP rate limits on auth, AI and general endpoints.
- **Audit.** Logins, verifications, safety reviews, flag changes, acceptances and deliveries are all written to `audit_logs`.
- **Headers.** The API sets nosniff, frame-deny and a referrer policy. The nginx container also adds a permissions policy that allows only the microphone (voice reporting) and geolocation.

## Testing

```bash
cd backend
pytest                                   # SQLite, ~2 s
TEST_DATABASE_URL=postgresql://localhost:5432/festiveplate_test pytest   # PostgreSQL
```

There are 48 tests:
- Safety rules, extraction, IST time handling, prediction
- 3-NGO matching and exclusions (unverified, out of range, wrong food type, no capacity)
- Privacy levels and RBAC
- The full donor → NGO → volunteer → delivery → receipt journey
- **Concurrent acceptance**: 3 threads behind a barrier, exactly one winner
- Expiry, flag defaults and overrides, demo labelling, system health honesty

Frontend: `npm run build` runs the TypeScript strict type-check plus the production build.

## API

- Interactive docs: `http://localhost:8000/docs`, or `http://localhost:8080/docs` through Docker
- Static spec: [`docs/openapi.json`](docs/openapi.json). Regenerate with:
  ```bash
  cd backend && python -c "import json;from app.main import app;json.dump(app.openapi(),open('../docs/openapi.json','w'),indent=2)"
  ```

## Deployment notes

### Hosted demo: Netlify (frontend) + Render (API + PostgreSQL)

Netlify serves the static React build. Requests to `/api/*` are proxied server-side to the Render API, so the browser only ever talks to the Netlify origin, and no backend URL or key ends up in the JS bundle.

1. **Render (backend):**
   - Go to https://dashboard.render.com, then **New → Blueprint**, and pick this repo. `render.yaml` creates `festiveplate-api` (free web service) and `festiveplate-db` (free Postgres).
   - Leave `SARVAM_API_KEY` and `FLAGSMITH_ENVIRONMENT_KEY` blank to run in demo mode. `JWT_SECRET` and `METRICS_TOKEN` are generated automatically.
   - On first boot the service runs migrations and seeds demo data. Check that `https://<service>.onrender.com/health` returns `{"status":"ok"}`.
2. **Netlify (frontend):**
   - Go to https://app.netlify.com, then **Add new site → Import from Git**, and pick this repo. `netlify.toml` already sets base `frontend`, build `npm ci && npm run build` and publish `dist`.
   - If Render assigned a URL other than `festiveplate-api.onrender.com`, update the two `to =` lines in `netlify.toml` and push.
3. Open the Netlify URL and log in with any demo account (password `Demo@12345`).

Free-tier caveats:
- The Render free service sleeps after about 15 minutes idle, so the first request can take about 30-50 s.
- Free Postgres expires after 30 days.
- Uploaded photos are stored on ephemeral disk and lost on restart.
- Netlify proxy requests time out after about 26 s.

### General


- Set `APP_ENV=production`, a strong `JWT_SECRET`, a managed PostgreSQL `DATABASE_URL`, and `CORS_ORIGINS` for your domain.
- Set `SEED_DEMO_DATA=false` in production.
- Put the nginx container (or any reverse proxy) behind TLS. Browsers allow microphone access only on HTTPS or localhost.
- Use persistent or object storage for `UPLOAD_DIR`.
- Rate limiting and request metrics are in-process. For multiple replicas, move them to Redis or the gateway, and scrape `/metrics` from every replica.

## Known limitations

- No live NudgeBee connection: the app exposes metrics, logs and incidents for it to ingest, and labels the AI SRE insight cards as simulated.
- Sarvam integration follows Sarvam's published REST API, but it has not been exercised against a live key; the automated tests cover the unconfigured and demo paths only.
- SMS is simulated, and there are no push notifications (in-app only).
- Travel time is estimated from straight-line distance at an average speed of 18 km/h; there is no routing API.
- The Docker images have not been build-tested in CI yet. The migrate, seed and serve sequence has been verified against PostgreSQL 16 directly.
- No email verification or password reset flow yet.

---

FestivePlate does not certify food safety. Receiving organisations are responsible for inspecting food before distribution.
