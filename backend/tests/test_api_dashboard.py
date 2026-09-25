"""GET /dashboard/stats -- HTTP-level, end-to-end against the real
pipeline (function-level formula tests live in
tests/test_dashboard_stats.py).

Publishes two reference database versions in turn to force one run into
each of the two identification outcomes the fixed real AB1 file
(3100.ab1) can plausibly reach without needing a second genuinely
different sample: a *full*-length matching reference (PASS) and a
*partial*-length one covering only the first chunk of the same sequence
(REVIEW REQUIRED, since coverage necessarily can't clear the default 90%
floor when the reference itself is shorter than that). empty.ab1
(already used elsewhere, e.g. test_api_execute.py) supplies a run that
never reaches usability_check or identification at all, to prove those
two rates' denominators are what reached the stage, not every run.
"""
import io
from pathlib import Path

import pytest


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


TRIMMED_3100 = (
    "AGCGATTCCAGCTTCATATAGTCGAGTTGCAGACTACAATCCGAACTGAGAACAACTTTATGGGATTTGCT"
    "TGACCTCGCGGTTTCGCTGCCCTTTGTATTGTCCATTGTAGCACGTGTGTAGCCCAAATCATAAGGGGCAT"
    "GATGATTTGACGTCATCCCCACCTTCCTCCGGTTTGTCACCGGCAGTCAACTTAGAGTGCCCAACTTAAT"
    "GATGGCAACTAAGCTTAAGGGTTGCGCTCGTTGCGGGACTTAACCCAACATCTCACGACACGAGCTGAC"
    "GACAACCATGCACCACCTGTCACTCTGTCCCCCGAAGGGGAAAACTCTATCTCTAGAGGAGTCAGAGGA"
    "TGTCAAGATTTGGTAAGGTTCTTCGCGTTGCTTCGAATTAAACCACATGCTCCACCGCTTGTGCGGGTC"
    "CCCGTCAATTCCTTTGAGTTTCAACCTTGCGGTCGTACTCCCCAGGCGGAGTGCTTAATGCGTTAGCTG"
    "CAGCACTAAGGGGCGGAAACCCCCTAACACTTAGCACTCATCGTTTACGGCGTGGACTACCAGGGTATC"
    "TAATCCTGTTTGATCCCCACGCTTTCGCACATCAGCGTCAGTTACAGACCAGAAAGTCGCCTTCGCCAC"
    "TGGTGTTCCTCCATATCTCTGCGCATTTCACCGCTACACAT"
)


def _publish(client, version, sequence, species):
    fasta_bytes = f">REF {species}\n{sequence}\n".encode()
    resp = client.post(
        "/reference-database/publish",
        files={"fasta": ("reference.fasta", io.BytesIO(fasta_bytes), "text/plain")},
        data={"version": version},
    )
    assert resp.status_code == 201, resp.text


def _create_and_execute(caller, fixtures_dir, filename, sample_id):
    create_resp = caller.post(
        "/runs",
        files={"forward_read": _file_field(fixtures_dir, filename)},
        data={"sample_id": sample_id},
    )
    run_id = create_resp.json()["id"]
    exec_resp = caller.post(f"/runs/{run_id}/execute")
    return run_id, exec_resp.json()


class TestRequiresAuthentication:
    def test_requires_a_token(self, anon_client):
        resp = anon_client.get("/dashboard/stats")

        assert resp.status_code == 401


class TestDashboardStatsEndToEnd:
    def test_stats_reflect_real_pipeline_outcomes_and_scope_by_caller(
        self, client, analyst_client, fixtures_dir, temp_reference_data_root
    ):
        # 1) A partial-length reference -- coverage can't clear the 90%
        #    floor, so this run reaches identification as REVIEW REQUIRED
        #    (a candidate exists, it just fails the quality bar), but
        #    still passes usability_check (the read itself is fine).
        _publish(client, "v1-partial", TRIMMED_3100[:300], "Partialus matchus")
        analyst_review_run_id, analyst_review_run = _create_and_execute(
            analyst_client, fixtures_dir, "3100.ab1", "ANALYST_review"
        )
        assert analyst_review_run["status"] == "completed"

        # 2) A full-length, exact-match reference -- PASS.
        _publish(client, "v2-full", TRIMMED_3100, "Testus fixturensis")
        analyst_pass_run_id, analyst_pass_run = _create_and_execute(
            analyst_client, fixtures_dir, "3100.ab1", "ANALYST_pass"
        )
        assert analyst_pass_run["status"] == "completed"

        admin_pass_run_id, admin_pass_run = _create_and_execute(
            client, fixtures_dir, "3100.ab1", "ADMIN_pass"
        )
        assert admin_pass_run["status"] == "completed"

        # 3) A run that fails before ever reaching usability_check or
        #    identification -- "processed", but shouldn't dilute either
        #    rate's denominator.
        _, analyst_failed_run = _create_and_execute(
            analyst_client, fixtures_dir, "empty.ab1", "ANALYST_sanity_fail"
        )
        assert analyst_failed_run["status"] == "failed"
        assert analyst_failed_run["current_stage"] == "sanity_check"

        # --- Analyst's own view: 3 runs, admin's 4th is invisible ---
        analyst_stats = analyst_client.get("/dashboard/stats").json()
        assert analyst_stats["total_samples_processed"] == 3
        assert analyst_stats["identification_rate"] == 0.5  # 1 PASS / 2 identification-stage runs
        assert analyst_stats["qc_pass_rate"] == 1.0  # 2 PASS / 2 usability-stage runs
        assert analyst_stats["pending_review_count"] == 1
        assert analyst_stats["species_breakdown"] == [
            {"species": "Testus fixturensis", "count": 1}
        ]
        histogram_total = sum(b["count"] for b in analyst_stats["quality_score_histogram"])
        assert histogram_total == 2  # the two runs that reached usability_check

        # --- Admin's view: all 4 runs across both users ---
        admin_stats = client.get("/dashboard/stats").json()
        assert admin_stats["total_samples_processed"] == 4
        assert admin_stats["identification_rate"] == pytest.approx(2 / 3)
        assert admin_stats["qc_pass_rate"] == 1.0  # 3 PASS / 3 usability-stage runs
        assert admin_stats["pending_review_count"] == 1
        species_counts = {row["species"]: row["count"] for row in admin_stats["species_breakdown"]}
        assert species_counts == {"Testus fixturensis": 2}
        admin_histogram_total = sum(b["count"] for b in admin_stats["quality_score_histogram"])
        assert admin_histogram_total == 3

