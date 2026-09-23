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
