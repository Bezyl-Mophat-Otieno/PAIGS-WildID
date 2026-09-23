# PAIGS — Project Instructions for Claude Code

## What this project is

PAIGS WildID: a Python backend that automates wildlife DNA species identification, replacing a manual Geneious-based workflow. Two AB1 sequencer files (forward + reverse read of one sample) go in; a species identification with a full audit trail comes out. This is headed toward forensic/evidentiary use, so **auditability and reproducibility are hard requirements, not nice-to-haves** — never silently overwrite a result, always log what was tried and with what parameters.

## Development method — strict TDD, one stage at a time

For every stage of the pipeline:
1. Write the test(s) first, against the stage's intended input/output contract (see "Stage list" below).
2. Run them — confirm they fail.
3. Implement the minimum code to pass.
4. Run again — confirm they pass.
5. Refactor if needed, tests still green.
6. Only then move to the next stage.

Do not implement a stage before its tests exist. Do not move to the next stage until the current one's tests pass. API endpoints must be tested through FastAPI's `TestClient` against real routes, not just as isolated unit functions.

## Tech stack

| Layer | Technology |
|---|---|
| Backend framework | Python + FastAPI, Pydantic for request/response schemas |
| AB1 parsing | Biopython (`Bio.SeqIO`) |
| QC numerics | NumPy |
| Orientation detection / consensus | Biopython (`Bio.Align.PairwiseAligner`) |
| Sequence search | BLAST+ (external binary, invoked as a subprocess — NOT a pip package; must be installed separately, e.g. via `apt` or a Docker base image) |
| Results ranking/filtering | pandas |
| Reporting | ReportLab (or WeasyPrint) |
| Database | PostgreSQL (SQLite acceptable for early prototype), SQLAlchemy |
| Frontend (later, not yet started) | React SPA |

## The Run/Stage model (core architecture)

A **Run** is one analyst's attempt to identify one sample. It is made of ordered **Stage** records — not function calls — each persisted independently with its own status and output, so any stage can be inspected or resumed without recomputing others.

```
Run: { id, sample_id, original_filenames: [a, b], created_at, current_stage, status }
Stage: { run_id, stage_type, status, input_ref, output, started_at, completed_at, metadata, attempt_number }
```

- `stage_type`: `import | ab1_extraction | qc | orientation | consensus | trim | fasta | blast | identification | report`
- `status`: `pending | running | completed | failed | skipped`
- **Never overwrite a stage's output.** A re-run with different parameters creates a new `attempt_number`; old attempts are kept.
- The backend enforces stage ordering (e.g. refuses to run BLAST if QC hasn't completed) — never trust this to a client.

## Stage list (build in this order)

0. **Import** — two AB1 files uploaded together, any order; creates the Run record. Filenames+timestamp become the default sample label.
1. **AB1 extraction** — per file, via Biopython: raw sequence + Phred quality scores.
2. **QC** — per file, independent: min length, min mean Phred quality, max ambiguous (`N`) base count. **Branching rule (current default): if one read passes and the other fails, fall back to single-read processing** (skip stages 3–4, flag the report "single-read, no consensus"). If both fail, the run stops. The stricter "stop and re-upload on any failure" alternative is a documented open option, not yet chosen.
3. **Orientation detection** *(only if both reads passed QC)* — pairwise-align read A vs read B, and read A vs reverse-complement(read B); whichever overlaps well determines orientation. No assumption about which uploaded file is forward/reverse.
4. **Consensus building** — merge the oriented pair position-by-position, picking the higher-confidence base at each spot. Positions where both reads disagree confidently are flagged as ambiguous, not silently resolved.
5. **Trimming** — remove remaining low-confidence leading/trailing ends (of the consensus, or of the single read in fallback mode).
6. **FASTA generation** — serialize the cleaned sequence to standard FASTA.
7. **BLAST comparison** — search FASTA against a curated reference database (built with `makeblastdb`, versioned separately from the app DB); capture identity %, coverage %, E-value, bit score per candidate.
8. **Identification engine** — apply *configurable* thresholds (never hardcoded — store in a config table) to classify: `PASS | AMBIGUOUS | REVIEW_REQUIRED`. Never accept the top BLAST hit uncritically.
9. **Reporting** — assemble every prior stage's data into an auditable PDF: QC results, orientation/consensus outcome (or single-read flag), reference DB version, all candidate scores, thresholds applied, final status, and stated limitations.

## API shape

```
POST   /runs                      -> create a run (upload 2 AB1 files, set label)
GET    /runs                      -> list runs (history)
GET    /runs/{id}                 -> run summary + all stage statuses
GET    /runs/{id}/stages/{type}   -> a specific stage's stored output
POST   /runs/{id}/stages/{type}   -> trigger execution of that stage
PATCH  /runs/{id}                 -> rename/relabel a run
```

Each `POST .../stages/{type}` runs exactly one stage and returns/stores its result — never the whole pipeline at once.

## Repo layout

```
backend/
  app/
    main.py
    models/            # SQLAlchemy models (Run, Stage, ReferenceEntry, ThresholdConfig)
    schemas/            # Pydantic contracts, one module per stage's input/output
    pipeline/
      ab1_extraction.py
      qc.py
      orientation.py
      consensus.py
      trimming.py
      fasta_gen.py
      blast_runner.py
      identification.py
      reporting.py
    api/
      runs.py
    db.py
  tests/
    test_ab1_extraction.py
    test_qc.py
    test_orientation.py
    test_consensus.py
    test_trimming.py
    test_fasta_gen.py
    test_blast_runner.py
    test_identification.py
    test_reporting.py
    test_api_runs.py
    fixtures/           # sample .ab1 files (3730.ab1, 3100.ab1, empty.ab1 to start)
  requirements.txt
```

## Conventions

- Every stage's input/output is a typed Pydantic model — defined *before* the stage is implemented, so integration bugs surface as validation errors, not silent bad data.
- Business thresholds (QC limits, identity/coverage cutoffs) live in configuration, not in code, since they belong to the domain experts and may differ per DNA marker/species.
- Original uploaded AB1 files are never modified, ever.
- Run test commands with `pytest -v` from `backend/`; keep tests fast — mock/stub the BLAST+ subprocess call in unit tests, reserve real BLAST+ invocation for a small set of integration tests.

## Known open decisions (do not assume an answer — ask if it matters for the task at hand)

- QC branching default is single-read fallback (see Stage 2 above), but the stricter alternative is still on the table for the domain team.
- Upload UX: one combined file input vs. two labeled inputs — leaning toward one combined input, not yet finalized (affects frontend only, not backend).
- Re-running a completed stage: view-only by default, explicit separate action to re-run with new parameters (creating a new `attempt_number`) — not yet finalized whether the API needs a distinct endpoint for this or reuses `POST .../stages/{type}` with a new-attempt flag.
- Whether QC failure should be its own 4th top-level status distinct from PASS/AMBIGUOUS/REVIEW_REQUIRED, or remain a run-ending condition at Stage 2 — open for the domain team.
