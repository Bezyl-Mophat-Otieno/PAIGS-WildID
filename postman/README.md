# PAIGS WildID -- Postman collection

Manual-testing companion to the automated pytest suite in `backend/tests/`.
Currently covers Stage 0 (Import) only -- one folder per stage will be added
here as the pipeline is built out.

Updated 2026-09-23 for the CLAUDE.md rewrite: upload now goes into two
independently-optional labeled slots, `forward_read` and `reverse_read` --
a single file is a first-class path, not a fallback.

## Setup

1. Start the API from `backend/`:

   ```
   pip install -r requirements.txt   # first time only
   uvicorn app.main:app --reload
   ```

   This serves on `http://127.0.0.1:8000` by default, matching the `base_url`
   in the environment file below.

2. In Postman: Import -> select both `PAIGS.postman_collection.json` and
   `PAIGS.postman_environment.json`. Select the "PAIGS Local" environment
   from the environment dropdown (top right).

3. Run the **Happy path** folder top to bottom first. The first request
   ("Create run - forward + reverse reads") saves the new run's id into the
   `run_id` environment variable, which every later request in the collection
   reuses.

4. The **Errors** folder can mostly be run independently and in any order,
   except "Patch run - rejects empty label", which also relies on `run_id`
   having been set by the happy path first.

## Test data

`test-data/` holds copies of the three fixture AB1 files used by the
automated tests (`3100.ab1`, `3730.ab1`, `empty.ab1`), plus
`not_a_sequence.txt`, a plain-text file used to manually exercise the
"rejects non-.ab1 upload" case. These are kept as copies (not references
into `backend/tests/fixtures/`) so this folder is self-contained.

## Notes

- Each run in this collection is stored for real (SQLite, `backend/paigs.db`,
  and files under `backend/storage/`) -- this is hitting your local dev
  database, not an isolated test database like pytest uses. Re-running the
  "Create run" requests repeatedly will accumulate runs; that's expected.
- `empty.ab1` isn't exercised by this collection yet -- it's reserved for
  Stage 3 (Coarse sanity check), where it's expected to fail.
- `forward_read` and `reverse_read` are independently optional -- Stage 0
  doesn't validate that a file placed in one slot is actually that read;
  a label/detected mismatch is only surfaced later, at Stage 5 (Orientation
  Detection), and never blocks the run.

## Authentication (added 2026-09-25)

Every `/runs` endpoint now requires a bearer token, and Runs are scoped per
owner -- see the backend README's own "Authentication" section for the
account model. This collection carries a collection-level Bearer auth using
the `admin_token` environment variable, which every request inherits
automatically (no per-request setup needed).

**Run the "Authentication & Admin" folder first**, top to bottom -- its
first request ("Admin login (seeded default account)") logs in as the
seeded default admin and captures `admin_token`. Every other folder's
requests depend on it being set, the same way "Happy path" needs to run
before requests that reuse `run_id`.
