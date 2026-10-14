"""Configuration subsystem -- service-layer tests (seeding, list, update,
effective-threshold resolution, and the stage-kwargs mapping), against a
raw DB session (db_session fixture) rather than the HTTP API -- that's
covered separately in test_api_config.py.
"""
import pytest

from app.configuration import service as config_service
from app.configuration.catalog import CATALOG, CATALOG_BY_KEY
from app.configuration.errors import (
    ConfigNotFoundError,
    ConfigValueNotAllowedError,
    ConfigValueOutOfBoundsError,
    UnknownConfigKeyError,
)
from app.models.config import ConfigThreshold


class TestEnsureSeeded:
    def test_seeds_one_row_per_catalog_key_with_its_default_value(self, db_session):
        config_service.ensure_seeded(db_session)
        rows = db_session.query(ConfigThreshold).all()
        assert len(rows) == len(CATALOG)
        by_key = {row.key: config_service.value_of(row) for row in rows}
        for definition in CATALOG:
            assert by_key[definition.key] == definition.default

    def test_numeric_keys_seed_into_the_value_column_and_non_numeric_into_value_text(
        self, db_session
    ):
        config_service.ensure_seeded(db_session)
        rows = {row.key: row for row in db_session.query(ConfigThreshold).all()}

        numeric_row = rows["trim.quality_threshold"]
        assert numeric_row.value == 20.0
        assert numeric_row.value_text is None

        enum_row = rows["blast.mode"]
        assert enum_row.value is None
        assert enum_row.value_text == "remote"

    def test_is_idempotent_and_never_overwrites_an_edited_value(self, db_session):
        config_service.ensure_seeded(db_session)
        row = db_session.query(ConfigThreshold).filter_by(key="trim.quality_threshold").one()
        row.value = 30.0
        db_session.commit()

        config_service.ensure_seeded(db_session)

        row = db_session.query(ConfigThreshold).filter_by(key="trim.quality_threshold").one()
        assert row.value == 30.0
        assert db_session.query(ConfigThreshold).count() == len(CATALOG)


class TestListConfig:
    def test_seeds_then_returns_every_row_sorted_by_key(self, db_session):
        rows = config_service.list_config(db_session)
        assert len(rows) == len(CATALOG)
        assert [r.key for r in rows] == sorted(r.key for r in rows)


class TestUpdateConfig:
    def test_updates_the_value_and_bumps_updated_at(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "usability_check.min_length")
        original_updated_at = row.updated_at

        updated = config_service.update_config(db_session, row.id, 600.0)

        assert updated.value == 600.0
        assert updated.updated_at >= original_updated_at

    def test_raises_for_unknown_id(self, db_session):
        config_service.ensure_seeded(db_session)
        with pytest.raises(ConfigNotFoundError):
            config_service.update_config(db_session, "does-not-exist", 1.0)

    def test_raises_for_out_of_bounds_proportion(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "sanity_check.max_n_proportion")
        with pytest.raises(ConfigValueOutOfBoundsError):
            config_service.update_config(db_session, row.id, 1.5)

    def test_raises_for_negative_count(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "usability_check.min_length")
        with pytest.raises(ConfigValueOutOfBoundsError):
            config_service.update_config(db_session, row.id, -1)

    def test_updates_an_enum_key_into_its_value_text_column(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "blast.mode")

        updated = config_service.update_config(db_session, row.id, "local")

        assert updated.value_text == "local"
        assert config_service.value_of(updated) == "local"

    def test_raises_for_a_disallowed_enum_value(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "blast.mode")
        with pytest.raises(ConfigValueNotAllowedError):
            config_service.update_config(db_session, row.id, "hybrid")


class TestValidateOverrides:
    def test_accepts_known_keys_within_bounds(self):
        config_service.validate_overrides({"usability_check.min_length": 400})

    def test_rejects_unknown_key(self):
        with pytest.raises(UnknownConfigKeyError):
            config_service.validate_overrides({"not_a_real_stage.not_a_real_param": 1})

    def test_rejects_out_of_bounds_value(self):
        with pytest.raises(ConfigValueOutOfBoundsError):
            config_service.validate_overrides({"orientation.min_identity": 2.0})

    def test_accepts_local_as_a_valid_blast_mode_override(self):
        config_service.validate_overrides({"blast.mode": "local"})

    def test_rejects_a_blast_mode_value_outside_its_choices(self):
        with pytest.raises(ConfigValueNotAllowedError):
            config_service.validate_overrides({"blast.mode": "hybrid"})

    def test_accepts_any_free_text_for_entrez_query(self):
        config_service.validate_overrides(
            {"blast.entrez_query": "NOT environmental sample[filter]"}
        )


class TestEffectiveThresholds:
    def test_returns_global_defaults_when_no_overrides_given(self, db_session):
        effective = config_service.effective_thresholds(db_session)
        for definition in CATALOG:
            assert effective[definition.key] == definition.default

    def test_reflects_a_prior_put_edit(self, db_session):
        rows = config_service.list_config(db_session)
        row = next(r for r in rows if r.key == "trim.quality_threshold")
        config_service.update_config(db_session, row.id, 25.0)

        effective = config_service.effective_thresholds(db_session)
        assert effective["trim.quality_threshold"] == 25.0

    def test_per_run_override_wins_over_the_global_value(self, db_session):
        effective = config_service.effective_thresholds(
            db_session, {"usability_check.min_length": 100}
        )
        assert effective["usability_check.min_length"] == 100
        # everything else still falls back to the global default
        assert effective["trim.quality_threshold"] == 20.0

    def test_raises_for_an_unknown_override_key(self, db_session):
        with pytest.raises(UnknownConfigKeyError):
            config_service.effective_thresholds(db_session, {"bogus.key": 1})


class TestKwargsForStage:
    def test_extracts_only_that_stages_keys_with_correct_param_names(self, db_session):
        effective = config_service.effective_thresholds(db_session)
        kwargs = config_service.kwargs_for_stage(effective, "sanity_check")
        assert kwargs == {
            "max_n_proportion": 0.5,
            "min_raw_length": 50,
        }

    def test_casts_int_typed_keys_back_to_python_int(self, db_session):
        effective = config_service.effective_thresholds(db_session)
        kwargs = config_service.kwargs_for_stage(effective, "trim")
        assert isinstance(kwargs["quality_threshold"], int)
        assert isinstance(kwargs["min_window_size"], int)

    def test_leaves_float_typed_keys_as_float(self, db_session):
        effective = config_service.effective_thresholds(db_session)
        kwargs = config_service.kwargs_for_stage(effective, "orientation")
        assert isinstance(kwargs["min_identity"], float)

    def test_blast_kwargs_include_the_search_mode_keys_alongside_max_hits(self, db_session):
        effective = config_service.effective_thresholds(db_session)
        kwargs = config_service.kwargs_for_stage(effective, "blast")
        assert kwargs == {
            "max_hits": 10,
            "mode": "remote",
            "remote_database": "core_nt",
            "entrez_query": "",
            "remote_timeout_seconds": 300,
        }
