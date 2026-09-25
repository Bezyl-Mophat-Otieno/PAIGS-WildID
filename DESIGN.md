# PAIGS WildID — Frontend Design Spec

Sep 25, 2026

An actionable build spec for the React frontend — paired with [`CLAUDE.md`](./CLAUDE.md) (the pipeline/backend spec). Where CLAUDE.md says what the system does, this says what it looks like and how it's built. Every screen below states exactly which backend endpoint powers it — build against those directly, don't mock data for anything marked **Ready**. Only one thing on this whole spec is not backend-ready yet (Validation Batches, flagged explicitly where it comes up) — request it rather than fake it.

Design inspiration: five mockup screenshots at `docs/designs/IMG-20260922-WA0011.jpg` through `WA0015.jpg` (Dashboard, New Analysis, Results Analysis, Reports, Home). Their visual language (dark sidebar, card-based stat tiles, stepper, tab-based detail panels) is the base to build from — this doc corrects the specific places they don't match the real API and fills in what they left unspecified (exact colors, chart types, badge states).

## Tech stack

- **React + Vite**
- **Tailwind CSS + shadcn/ui** — owned, restylable components rather than a themed black-box library, since we have an exact brand palette and badge system below
- **Recharts** for standard charts (funnel, bars, donut, histogram); hand-rolled SVG for the chromatogram trace specifically, since it's a custom multi-channel signal plot no standard chart type covers
- **TanStack Table** for sortable/filterable lists (runs, reports, config, reference versions)
- **TanStack Query** for data fetching — its `refetchInterval` is what drives the live stage stepper (CLAUDE.md: "the frontend polls `GET /runs/{id}` to drive the live stepper")
- **React Hook Form + Zod** for the upload and config-override forms
- **react-dropzone** for the dual-file upload pattern (see below)
- **axios** with a request interceptor attaching the bearer token, plus React Context for the current user/role
- **React Router**

## Visual design system

### Brand chrome

Sampled from the mockups — approximate, worth confirming against the original design file rather than treating as pixel-exact:

| Role | Value |
| --- | --- |
| Sidebar / dark surface | `#122A1D` (deep forest green) |
| Primary action (buttons, active nav, links) | `#1E7A46` |
| Page background | `#F9F9F7` |
| Card surface | `#FFFFFF`, hairline border `#E1E0D9` |
| Primary text | `#0B0B0B` |
| Secondary / muted text | `#52514E` / `#898781` |

### Status colors — fixed, reserved, never reused for anything else

Run through the project's dataviz accessibility validator rather than eyeballed. Two of the four sit under 3:1 contrast on a light surface by design — **every status badge must pair its color with an icon and a text label, never color alone.**

| Status | Hex | Maps to |
| --- | --- | --- |
| good | `#0ca30c` | PASS (sanity check, usability check, identification) |
| warning | `#fab219` | AMBIGUOUS (identification only) |
| serious | `#ec835a` | REVIEW REQUIRED (identification only) |
| critical | `#d03b3b` | FAILED / run stopped |

### Categorical (multi-series charts, e.g. the dashboard's species breakdown)

Validated 8-hue order: blue → orange → aqua → yellow → magenta → green → violet → red. Only the **first 3 hues are safe for an all-pairs chart** (a donut, where every slice sits beside every other) — past 3 categories, fold the rest into "Other" or keep direct percentage labels beside each legend entry (the mockup's donut already does this, which is what makes going past 3 legal there).

### Sequential (a single ramp for magnitude — quality heatmaps, the funnel, the trim chart's quality trace)

Default blue ramp, deliberately **not** brand green — reusing green for both "this is brand chrome" and "this is a quality signal" would blur two different meanings onto one hue.

### Typography

System sans everywhere (`system-ui, -apple-system, "Segoe UI", sans-serif`), including the dashboard's large KPI numbers — no display/serif face. Tabular figures only where values must align vertically (results table, BLAST hit-rank table); everywhere else uses normal proportional figures.

### The heavy-on-visuals mandate

Wherever a stage's output is a set of comparable numbers, it renders as a chart first, with the raw numbers underneath as a caption or expandable detail — never the reverse. The Trim panel leads with its quality-trace chart, not a table of `trim_start`/`trim_end` with a chart bolted on after. Same rule for the BLAST hit comparison, the pipeline funnel, and the consensus alignment view.

## Frontend architecture

- **Layout shell:** persistent left sidebar (nav + role-aware menu items) + top bar (search, notifications, user menu) + content area — matches every mockup screen.
- **Routing:** run list → run detail (tab-based inspector, stage tabs) → individual stage panels. Not a wizard — CLAUDE.md is explicit about this: any completed stage opens instantly, read-only, no recomputation.
- **Data fetching:** TanStack Query for everything. A run's detail view polls `GET /runs/{id}` on an interval while `status === "in_progress"`, stops polling once it's `completed` or `failed`.
- **Auth:** token from `POST /auth/login` stored in memory/sessionStorage (not localStorage, to limit XSS exposure), attached via an axios interceptor to every request. `GET /auth/me` on app load to restore session and get the current role.
- **State:** no global state library needed beyond TanStack Query's cache + a small Context for the authenticated user — nothing else in this app has state complex enough to need Redux/Zustand.

## Role-based behavior — visibility vs. authority

The backend enforces a **visibility ≠ authority** split, and the frontend must reflect it exactly, not just hide a nav item:

- An **admin can view** any user's Run, chromatogram, stage detail, and report (`GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/stages/{type}`, `GET /runs/{id}/chromatogram/{slot}`, `GET /runs/{id}/report`, `GET /dashboard/stats`, `GET /runs/reports/export` all include every user's data for an admin).
- An admin **cannot act on** another user's Run — `POST /runs/{id}/execute`, `POST /runs/{id}/rerun`, and `PATCH /runs/{id}` are owner-only, full stop, no admin override. **The UI must hide Execute/Rerun/Rename controls on any run the viewing admin doesn't own**, even though they can see everything else about it. Showing those buttons and letting the backend 404 them is the wrong failure mode — don't render them at all.
- An analyst sees and acts on only their own Runs — no visibility into anyone else's, ever.
- `RunRead` includes `owner_id` but **not** an owner name/email — to show "who ran this" in an admin's all-runs view, the frontend must separately call `GET /admin/users` and join by id client-side. Worth building as a small shared lookup hook, not repeated per-screen.
- Global config (`PUT /config/{id}`) and reference-database publishing (`POST /reference-database/publish`) are **admin-only writes**; both are readable by any authenticated user (`GET /config`, `GET /reference-database/versions`, `GET /reference-database/active`) since an analyst needs to see current thresholds/active DB when interpreting a run.
- **Team / Users** (invite a user, list users — `POST /admin/invite`, `GET /admin/users`) is the one screen admin gets that analyst doesn't.

## Upload flow: single vs. dual-file

**Don't make the analyst pick a "mode."** A toggle between "Single Read" and "Forward + Reverse" would visually frame single-file as the lesser of two paths — CLAUDE.md is explicit that a single file is a fully-supported, first-class entry point, not a degraded fallback.

The pattern:

1. One dropzone/browse control accepting **one or two files at once** (standard multi-select, like a Gmail attachment picker).
2. Files resolve into two labeled slots — **Forward Read** / **Reverse Read** — in drop order, each with a swap control.
3. If only one file lands, the second slot shows a quiet **"+ Add reverse read (optional)"** affordance plus the line **"A single read is a complete, valid analysis on its own."**
4. A persistent note under both slots: **"Forward/Reverse labels are a starting guess — the system detects true orientation automatically and will flag it if your labels don't match, without blocking the run."**

This maps one-to-one onto `POST /runs`'s real contract: `forward_read` and `reverse_read` are both optional, independent form fields, and at least one is required.

## Screens

Every screen below is **Ready** — build against the live API now — unless marked otherwise.

### 1. Login

`POST /auth/login` (OAuth2 form fields — `username` doubles as email). Store the returned `access_token` + `role`. No self-registration screen exists or should be built — accounts are invite-only.

### 2. Dashboard / Home

`GET /dashboard/stats` → `total_samples_processed`, `identification_rate` (nullable — render "—" not "0%" when null, meaning no run has reached that stage yet), `qc_pass_rate` (nullable, same rule), `pending_review_count`, `species_breakdown[]`, `quality_score_histogram[]`. Scoped automatically by the backend (admin = everyone, analyst = own) — no client-side filtering needed.

- KPI tiles: samples processed, identification rate, QC pass rate, pending review count.
- Species breakdown → donut, capped at 3 direct-labeled categories + "Other" per the categorical color rule above, PASS-only identifications.
- Quality histogram → bar chart, 5 fixed buckets (`<20`, `20-25`, `25-30`, `30-35`, `35+`), covers every usability-check stage regardless of pass/fail.

### 3. New Analysis (upload)

`POST /runs` (multipart: `forward_read`, `reverse_read`, `sample_id`, `config_overrides` as a JSON string) then `POST /runs/{id}/execute`.

**Threshold fields must be pre-filled from `GET /config`, not left blank.** Fetch the current global defaults on page load and render all **13** catalogued values (label/description/bounds come straight from that response — don't hardcode them) under an "Advanced" expansion. Track which fields the analyst actually edits: only the *touched* ones go into the `config_overrides` payload sent to `POST /runs` — an untouched field is left out entirely, never resubmitted at its default value. This matters for two reasons: it keeps `Run.config_overrides` a true, sparse record of what was deliberately changed (CLAUDE.md's "a deliberate choice, not silent inheritance" — not "every value the analyst happened to see that day"), and it means a later global-default change never retroactively looks like it was this run's own choice. Visibly mark an edited field (a small "Modified" tag + a reset-to-default control) so the distinction is obvious while filling the form, not just in the submitted payload.

### 4. Run detail (tab-based inspector)

`GET /runs/{id}` drives the stepper (poll while `in_progress`); `GET /runs/{id}/stages/{stage_type}` per stage tab, read-only, no recomputation. `stage_type` ∈ `import, format_check, ab1_extraction, sanity_check, trim, orientation, consensus, usability_check, fasta, blast, identification, report`. Stepper must represent all 12, visibly branching (Orientation + Consensus grayed/"skipped") on the single-read path.

- `GET /runs/{id}/chromatogram/{slot}` (`slot` = `forward`/`reverse`) → raw 4-channel trace for the chromatogram viewer.
- `GET /runs/{id}/report` → streams the PDF directly (`Content-Type: application/pdf`).
- `PATCH /runs/{id}` → relabel (owner only).
- **"Thresholds used" panel** — there's no single field that hands back a run's full effective 13-value set; reconstruct it the same way the PDF report's own "Other Thresholds Applied" section does, by reading each relevant stage's own record: `trim` stage's `output.trim_params`, the `orientation`/`sanity_check`/`usability_check`/`blast` stages' `stage_metadata.thresholds`, and the `identification` stage's `output.thresholds_applied`. Build this as one shared helper (not repeated per-screen) since it's also what the Rerun screen below needs.

### 5. Rerun comparison

`POST /runs/{id}/rerun` (`{config_overrides, sample_id, auto_execute}`) creates a sibling Run; the new Run's `rerun_of` points back at the source. Read both Runs and render side by side — this is a net-new screen, nothing in the mockups covers it.

**Pre-fill the rerun form from the source Run's own effective thresholds — not the current global defaults, and not blank.** Global config can drift between when the source Run executed and when someone reruns it, so "current defaults" isn't the same as "what this run actually used." Reuse the "Thresholds used" reconstruction from Run detail above to compute the source Run's real starting values. Same touched/untouched distinction as New Analysis applies to the rerun form itself. Once both Runs exist, the side-by-side view should highlight exactly which of the 13 keys actually differ between them, not just list each Run's values in isolation.

### 6. Run history (list)

`GET /runs` — already scoped server-side (admin = all, analyst = own). Filter/sort client-side via TanStack Table.

### 7. Reports

Per-run: `GET /runs/{id}/report`. Bulk: `GET /runs/reports/export?run_ids=...` (omit `run_ids` entirely for "export all") → a ZIP, scoped the same as the run list. Runs with no completed report are silently excluded from the zip, not an error — only a genuinely empty result (nothing exportable at all) 404s.

### 8. Configuration

`GET /config` (any authenticated user) / `PUT /config/{id}` (admin only). List all 13 thresholds with their label/description/bounds (already defined server-side — render directly from the response, don't hardcode labels client-side).

Editing a default here changes the baseline for every future run from every user, not just the person editing it — materially higher blast radius than a per-run override, which is exactly why `config_overrides` on `POST /runs` was never gated the same way and analysts can still read (not write) this whole screen. **No edit history exists yet** — `PUT /config/{id}` overwrites in place, so the UI can show when a value last changed (`updated_at`) but not who changed it or what it was before. Don't build a history/diff view for this; there's no data behind it to show.

### 9. Reference database

`GET /reference-database/versions`, `GET /reference-database/active` (any authenticated user); `POST /reference-database/publish` (admin only, `{fasta, version}` multipart) — publishing is synchronous and can take a moment for a large FASTA, show a real loading state.

### 10. Team / Users (admin only)

`POST /admin/invite` (`{email, role}`) returns a one-time `temporary_password` — email delivery is stubbed, so **this password must be shown to the admin to copy and share manually**, there is no other way for the invited user to get it. `GET /admin/users` lists everyone (no passwords exposed).

### 11. Validation Batches — **not backend-ready, request it**

CLAUDE.md's Validation feature (run known-answer sample batches, get an accuracy/ambiguity/reproducibility scorecard) has **no backend implementation at all yet** — no `POST /validation-batches`, no scoring logic, nothing. Do not build this screen against mocked data. Flag it as the one remaining backend request from this spec; once the endpoint exists, this doc will get a real section for it the same way every other screen has one.

## Stage status & badge system

Two different axes — keep them visually distinct so an analyst never confuses "this step broke" with "this step found something worth reviewing."

**Stage execution status** (`Stage.status`): `pending` (grey outline) · `running` (spinner, rare — execution is synchronous) · `completed` (green check, regardless of biological verdict) · `failed` (red, a genuine technical failure) · `skipped` (grey dashed — Orientation/Consensus on the single-read path, "not applicable" not "failed").

**Biological verdict** (shown inside a completed stage's own panel, not on the stepper icon):

| Verdict | Where | Color |
| --- | --- | --- |
| PASS | Sanity, Usability, Identification | `#0ca30c` |
| FAIL | Sanity, Usability — this is what actually ends the run | `#d03b3b` |
| AMBIGUOUS | Identification only | `#fab219` |
| REVIEW REQUIRED | Identification only | `#ec835a` (visibly deeper than AMBIGUOUS) |
| no overlap found | Orientation | Neutral/informational, not an error |

## Charts & visualizations

| Chart | Stage | Data source | Spec |
| --- | --- | --- | --- |
| Trim / quality trace | 4 | `quality_scores`, `trim_start`/`trim_end` from `ab1_extraction` + `trim` stages | 2px line, sequential blue ramp, across the full raw length; light fill wash under the kept window; trimmed-away portions in muted `#898781`, no fill — reads "kept vs. cut" with no legend needed |
| Chromatogram viewer | any, on demand | `GET /runs/{id}/chromatogram/{slot}` → `channel_order`, `trace` (per-base-letter intensity arrays), `peak_locations`, `base_calls` | 4 overlaid line traces (one per channel/base), called-base peak markers at `peak_locations`; zoom/pan to a flagged position |
| Consensus alignment | 6 | `consensus` stage's `resolved_positions[]` (`forward_base`, `reverse_base`, `resolved_base`, `changed`, `method`) + `ambiguous_positions[]` | Position-aligned two-row view, color-coded by `method` (agreement / ambiguity_consistency / quality_tiebreak) and by unresolved-ambiguous |
| BLAST hit comparison | 9/10 | `blast` stage's ranked `hits[]` | Grouped bars: identity % / coverage % per hit, `identification.thresholds_applied.ambiguous_margin_pct` drawn as a reference line |
| Pipeline funnel | all | `raw_length` → `trimmed_length` → `consensus_length` → `final_length` across stages | Funnel/bar, sequential ramp |
| Species breakdown | dashboard | `dashboard/stats` `species_breakdown[]` | Donut, capped at 3 + "Other" (see categorical color rule) |
| Quality histogram | dashboard | `dashboard/stats` `quality_score_histogram[]` | Bar, 5 fixed buckets |

## Reference

- Backend spec: [`CLAUDE.md`](./CLAUDE.md)
- Mockup screenshots: `docs/designs/IMG-20260922-WA0011.jpg` (Dashboard) · `WA0012.jpg` (New Analysis) · `WA0013.jpg` (Results Analysis) · `WA0014.jpg` (Reports) · `WA0015.jpg` (Home)
- Full config catalog (13 thresholds, all served with label/description/bounds via `GET /config` — don't hardcode these client-side): `sanity_check.max_n_proportion`, `sanity_check.min_raw_length`, `trim.quality_threshold`, `trim.min_window_size`, `orientation.min_overlap_length`, `orientation.min_identity`, `usability_check.min_length`, `usability_check.min_mean_quality`, `usability_check.max_ambiguous_proportion`, `blast.max_hits`, `identification.min_identity_pct`, `identification.min_coverage_pct`, `identification.ambiguous_margin_pct`.
