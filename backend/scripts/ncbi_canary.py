#!/usr/bin/env python3
"""
NCBI remote-BLAST canary -- a scheduled early-warning check, not part of
the app's own request-serving or background-poller code paths.

What it's for: app.pipeline.ncbi_remote parses NCBI's actual response
format by hand (RID/RTOE/status extraction from an HTML comment block,
BlastOutput2 XML for results) -- see that module's own docstring. If NCBI
ever changes that format again, the first sign of it today would be a
real analyst's run failing at Stage 9. This script submits a tiny, known,
real query against NCBI on a schedule (see
.github/workflows/ncbi-canary.yml) and fails loudly -- with the actual
raw response attached -- the moment any of submit/poll/fetch stops
working, so that's caught by a scheduled check instead of a production
incident.

Deliberately a standalone script with its own blocking poll loop, not a
reuse of app.orchestration.execute's non-blocking state machine -- that
machinery exists to avoid blocking a request-serving thread/DB
connection, neither of which applies here; a script that's allowed to
just wait is the simplest correct thing.

Usage:
    python scripts/ncbi_canary.py
Exit code 0 on success, 1 on any failure (bad RID, NCBI-reported failure,
unrecognized response shape, or exceeding --max-wait).
"""
import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.pipeline import ncbi_remote  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ncbi_canary")

# A real 200bp fragment of NC_001422.1 (Escherichia phage phiX174) --
# small, stable (a decades-old, unchanging reference genome), and
# guaranteed to produce real hits against NCBI's own databases, since
# it's a fragment of a sequence NCBI itself hosts.
CANARY_QUERY = (
    ">ncbi_canary_phix174_1-200\n"
    "GAGTTTTATCGCTTCCATGACGCAGAAGTTAACACTTTCGGATATTTCTGATGAGTCGAAAAATTATCTT"
    "GATAAAGCAGGAATTACTACTGCTTGTTTACGAATTAAATCGAAGTGGACTGCTGGCGGAAAATGAGAAA"
    "ATTCGACCTATCCTTGCGCAGCTCGAGAAGCTCTTACTTTGCGACCTTTCGCCATCAACT\n"
)


def run_canary(*, database: str, max_wait_seconds: int) -> bool:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as tmp:
        tmp.write(CANARY_QUERY)
        query_path = Path(tmp.name)

    try:
        logger.info("Submitting canary query to NCBI (database=%s)...", database)
        try:
            submission = ncbi_remote.submit_search(query_path, database=database, max_hits=5)
        except ncbi_remote.NcbiSubmissionFailedError:
            logger.exception("Submission failed -- NCBI did not return a usable RID.")
            return False

        logger.info("Submitted. RID=%s RTOE=%ss", submission.rid, submission.rtoe)

        wait_seconds = min(
            max(submission.rtoe or ncbi_remote.DEFAULT_POLL_INTERVAL_SECONDS, 5), 60
        )
        deadline = time.monotonic() + max_wait_seconds
        time.sleep(wait_seconds)

        while True:
            try:
                status = ncbi_remote.check_status(submission.rid)
            except (ncbi_remote.NcbiSearchFailedError, ncbi_remote.UnrecognizedNcbiResponseError):
                logger.exception("Status check failed for RID %s.", submission.rid)
                return False

            logger.info("RID %s status=%s", submission.rid, status)
            if status == "READY":
                break

            if time.monotonic() >= deadline:
                logger.error(
                    "RID %s did not become READY within %ss.", submission.rid, max_wait_seconds
                )
                return False

            time.sleep(ncbi_remote.DEFAULT_POLL_INTERVAL_SECONDS)

        try:
            result = ncbi_remote.fetch_result(submission.rid, max_hits=5)
        except (ncbi_remote.NcbiSearchFailedError, ncbi_remote.UnrecognizedNcbiResponseError):
            logger.exception("Result fetch/parse failed for RID %s.", submission.rid)
            return False

        if not result.hits:
            logger.error(
                "RID %s returned zero hits for a query expected to match -- "
                "possible silent format drift even though parsing succeeded.",
                submission.rid,
            )
            return False

        logger.info(
            "Success: %d hit(s), top hit %s (%.1f%% identity).",
            len(result.hits),
            result.hits[0].accession,
            result.hits[0].identity,
        )
        return True
    finally:
        query_path.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="nt", help="NCBI database to search (default: nt)")
    parser.add_argument(
        "--max-wait", type=int, default=600, help="Max seconds to wait for READY (default: 600)"
    )
    args = parser.parse_args(argv)

    ok = run_canary(database=args.database, max_wait_seconds=args.max_wait)
    if not ok:
        logger.error("NCBI canary FAILED.")
        return 1
    logger.info("NCBI canary PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
