#!/usr/bin/env python3
"""
CLI wrapper for Reference Database Setup (Part A).

A thin argument-parsing shell around app.reference.publish.publish_reference_db
-- all real logic lives there so a future admin-UI endpoint
(POST /reference-database/publish) can call the exact same function this
script calls, with no duplicated logic. See
claude/reference-database-setup-status.md for the full design.

Usage:
    python scripts/publish_reference_db.py --fasta reference_v3.fasta --version v3
"""
import argparse
import sys
from pathlib import Path

# So `app.*` imports resolve whether this is run as `python scripts/publish_reference_db.py`
# from backend/ or invoked by its absolute path from elsewhere.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.reference.publish import InvalidReferenceFastaError, publish_reference_db  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish a new PAIGS WildID reference database version from a curated FASTA."
    )
    parser.add_argument(
        "--fasta", required=True, type=Path, help="Path to the curated reference FASTA file."
    )
    parser.add_argument(
        "--version", required=True, help="Version label for this reference database, e.g. v3."
    )
    args = parser.parse_args(argv)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = publish_reference_db(args.fasta, args.version, db=db)
    except InvalidReferenceFastaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 -- surface makeblastdb/DB failures plainly on the CLI
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(
        f"Published reference database version {result.version!r}: "
        f"{result.sequence_count} sequence(s), index at {result.db_prefix}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
