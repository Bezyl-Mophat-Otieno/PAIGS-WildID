"""app.dashboard.stats.compute_dashboard_stats -- function-level tests.

Written first, against the not-yet-existing app.dashboard.stats module,
to confirm red before implementing. Builds Run/Stage/User rows directly
(same `db_session` pattern as tests/test_orchestration.py's `_make_run`)
rather than going through the real pipeline, so every input (stage
status, mean_quality, candidate_species) is exactly controlled -- the
HTTP-level tests in tests/test_api_dashboard.py separately prove this
wiring works against real, pipeline-produced Stage rows end-to-end.

See app.dashboard.stats's own module docstring for the reasoning behind
each of the six numbers' exact formula.
"""
from app.dashboard.stats import compute_dashboard_stats
from app.models.run import Run
from app.models.stage import Stage
from app.models.user import User


def _make_user(db_session, user_id, role="analyst"):
    user = User(
        id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="not-a-real-hash",
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_run(db_session, owner_id, status="in_progress", sample_id="WILD_TEST"):
    run = Run(
        sample_id=sample_id,
        original_filenames=["forward.ab1"],
        current_stage="import",
        status=status,
        owner_id=owner_id,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _make_stage(db_session, run_id, stage_type, output, status="completed"):
    stage = Stage(run_id=run_id, stage_type=stage_type, status=status, output=output)
    db_session.add(stage)
    db_session.flush()
    return stage


class TestEmpty:
    def test_no_runs_at_all_returns_zeroed_stats_not_an_error(self, db_session):
        user = _make_user(db_session, "u1")

        stats = compute_dashboard_stats(db_session, user)

        assert stats.total_samples_processed == 0
        assert stats.identification_rate is None
        assert stats.qc_pass_rate is None
        assert stats.pending_review_count == 0
        assert stats.species_breakdown == []
        assert all(bucket.count == 0 for bucket in stats.quality_score_histogram)

    def test_a_run_that_was_only_uploaded_never_executed_is_not_processed(self, db_session):
        user = _make_user(db_session, "u1")
        _make_run(db_session, "u1", status="in_progress")

        stats = compute_dashboard_stats(db_session, user)

        assert stats.total_samples_processed == 0
        assert stats.identification_rate is None
        assert stats.qc_pass_rate is None


class TestRatesAndCounts:
    def test_identification_rate_denominator_excludes_runs_that_never_reached_it(self, db_session):
        user = _make_user(db_session, "u1")

        # Reached identification, PASS.
        run_a = _make_run(db_session, "u1", status="completed", sample_id="A")
        _make_stage(
            db_session, run_a.id, "usability_check",
            {"status": "PASS", "mean_quality": 32.0, "final_length": 600, "ambiguous_positions": 0},
        )
        _make_stage(
            db_session, run_a.id, "identification",
            {"status": "PASS", "candidate_species": "Testus fixturensis", "thresholds_applied": {}},
        )

        # Stopped at sanity_check -- never reached usability_check or
        # identification at all. Still "processed" (status != in_progress).
        run_b = _make_run(db_session, "u1", status="failed", sample_id="B")

        stats = compute_dashboard_stats(db_session, user)

        assert stats.total_samples_processed == 2
        assert stats.identification_rate == 1.0  # 1 PASS / 1 identification-stage run, not / 2
        assert stats.qc_pass_rate == 1.0  # 1 PASS / 1 usability-stage run

    def test_review_required_counts_as_pending_review_and_is_excluded_from_species_breakdown(
        self, db_session
    ):
        user = _make_user(db_session, "u1")
        run = _make_run(db_session, "u1", status="completed", sample_id="C")
        _make_stage(
            db_session, run.id, "usability_check",
            {"status": "PASS", "mean_quality": 28.0, "final_length": 600, "ambiguous_positions": 0},
        )
        _make_stage(
            db_session, run.id, "identification",
            {
                "status": "REVIEW REQUIRED",
                "candidate_species": "Partialus matchus",
                "thresholds_applied": {},
            },
        )

        stats = compute_dashboard_stats(db_session, user)

        assert stats.pending_review_count == 1
        assert stats.identification_rate == 0.0
        assert stats.species_breakdown == []  # only PASS counts here

    def test_ambiguous_does_not_count_as_pending_review(self, db_session):
        user = _make_user(db_session, "u1")
        run = _make_run(db_session, "u1", status="completed")
        _make_stage(
            db_session, run.id, "identification",
            {"status": "AMBIGUOUS", "candidate_species": "Ambiguus maybeus", "thresholds_applied": {}},
        )

        stats = compute_dashboard_stats(db_session, user)

        assert stats.pending_review_count == 0
        assert stats.species_breakdown == []  # AMBIGUOUS isn't PASS either

    def test_species_breakdown_counts_pass_identifications_grouped_by_species(self, db_session):
        user = _make_user(db_session, "u1")
        for sample_id, species in [("A", "Fox"), ("B", "Fox"), ("C", "Wolf")]:
            run = _make_run(db_session, "u1", status="completed", sample_id=sample_id)
            _make_stage(
                db_session, run.id, "identification",
                {"status": "PASS", "candidate_species": species, "thresholds_applied": {}},
            )

        stats = compute_dashboard_stats(db_session, user)

        counts = {row.species: row.count for row in stats.species_breakdown}
        assert counts == {"Fox": 2, "Wolf": 1}


class TestQualityHistogram:
    def test_buckets_mean_quality_into_the_expected_ranges(self, db_session):
        user = _make_user(db_session, "u1")
        values = [15.0, 22.0, 27.0, 32.0, 40.0]
        for i, mean_quality in enumerate(values):
            run = _make_run(db_session, "u1", status="completed", sample_id=f"R{i}")
            _make_stage(
                db_session, run.id, "usability_check",
                {"status": "PASS", "mean_quality": mean_quality, "final_length": 600, "ambiguous_positions": 0},
            )

        stats = compute_dashboard_stats(db_session, user)

        counts = {bucket.label: bucket.count for bucket in stats.quality_score_histogram}
        assert counts == {"<20": 1, "20-25": 1, "25-30": 1, "30-35": 1, "35+": 1}

    def test_bucket_boundaries_are_lower_inclusive_upper_exclusive(self, db_session):
        user = _make_user(db_session, "u1")
        for sample_id, mean_quality in [("A", 20.0), ("B", 25.0), ("C", 30.0), ("D", 35.0)]:
            run = _make_run(db_session, "u1", status="completed", sample_id=sample_id)
            _make_stage(
                db_session, run.id, "usability_check",
                {"status": "PASS", "mean_quality": mean_quality, "final_length": 600, "ambiguous_positions": 0},
            )

        stats = compute_dashboard_stats(db_session, user)

        counts = {bucket.label: bucket.count for bucket in stats.quality_score_histogram}
        # Each exact boundary value belongs to the bucket it's the lower
        # edge of, not the one below.
        assert counts == {"<20": 0, "20-25": 1, "25-30": 1, "30-35": 1, "35+": 1}


class TestScoping:
    def test_admin_sees_every_users_runs(self, db_session):
        admin = _make_user(db_session, "admin-1", role="admin")
        _make_user(db_session, "analyst-1", role="analyst")
        _make_run(db_session, "admin-1", status="completed", sample_id="ADMIN_RUN")
        _make_run(db_session, "analyst-1", status="completed", sample_id="ANALYST_RUN")

        stats = compute_dashboard_stats(db_session, admin)

        assert stats.total_samples_processed == 2

    def test_an_analyst_only_sees_their_own_runs(self, db_session):
        _make_user(db_session, "admin-1", role="admin")
        analyst = _make_user(db_session, "analyst-1", role="analyst")
        _make_run(db_session, "admin-1", status="completed", sample_id="ADMIN_RUN")
        _make_run(db_session, "analyst-1", status="completed", sample_id="ANALYST_RUN")

        stats = compute_dashboard_stats(db_session, analyst)

        assert stats.total_samples_processed == 1
