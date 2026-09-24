"""Shared default-sample-id derivation.

Used by both POST /runs (a brand-new upload, app.api.runs.create_run)
and POST /runs/{id}/rerun (a new Run reusing a prior one's file(s),
app.orchestration.rerun.create_rerun) -- factored out on its own so
rerun doesn't have to import a private helper out of app.api.runs, or
duplicate the logic.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import List


def default_sample_id(filenames: List[str]) -> str:
    """Filenames + timestamp become the default sample label (CLAUDE.md Stage 0)."""
    stems = [Path(name).stem for name in filenames]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "_".join([*stems, timestamp])
