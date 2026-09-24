"""
Filesystem storage for uploaded AB1 files.

Files are stored under STORAGE_ROOT/runs/<run_id>/<original_filename>, copied
byte-for-byte and never modified afterward, per CLAUDE.md's "Original uploaded
AB1 files are never modified, ever" convention.

STORAGE_ROOT defaults to backend/storage/ (gitignored). Tests monkeypatch this
module attribute to redirect storage into an isolated tmp directory per test.
"""
import os
import shutil
from pathlib import Path
from typing import List

STORAGE_ROOT = Path(
    os.environ.get("PAIGS_STORAGE_ROOT", Path(__file__).resolve().parent.parent / "storage")
)


def run_dir(run_id: str) -> Path:
    return STORAGE_ROOT / "runs" / run_id


def save_uploaded_files(run_id: str, files) -> List[str]:
    """
    Save each uploaded file under run_dir(run_id), byte-for-byte.
    Returns the stored filenames, in the same order as `files`.
    """
    target_dir = run_dir(run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_names = []
    for upload in files:
        dest_name = _unique_name(target_dir, upload.filename)
        dest_path = target_dir / dest_name
        upload.file.seek(0)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(upload.file, out)
        stored_names.append(dest_name)
    return stored_names


def copy_run_files(source_run_id: str, dest_run_id: str, filenames: List[str]) -> List[str]:
    """
    Copy already-stored files from one run's directory into another's,
    byte-for-byte -- used by POST /runs/{id}/rerun
    (app.orchestration.rerun.create_rerun) to reuse a prior run's
    uploaded AB1 file(s) under the new run's own id, so every Run's
    storage directory stays self-contained (the same convention
    save_uploaded_files establishes for a fresh upload) and the analyst
    can try different configuration without re-uploading anything.
    Returns the stored filenames actually written in the destination
    directory, same order as `filenames` -- not necessarily identical to
    `filenames` if the destination directory somehow already held a file
    of the same name (see _unique_name).
    """
    source_dir = run_dir(source_run_id)
    target_dir = run_dir(dest_run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_names = []
    for filename in filenames:
        dest_name = _unique_name(target_dir, filename)
        shutil.copyfile(source_dir / filename, target_dir / dest_name)
        stored_names.append(dest_name)
    return stored_names


def _unique_name(target_dir: Path, filename: str) -> str:
    """Avoid collisions if both uploads happen to share a filename."""
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while (target_dir / candidate).exists():
        candidate = f"{stem}__{counter}{suffix}"
        counter += 1
    return candidate
