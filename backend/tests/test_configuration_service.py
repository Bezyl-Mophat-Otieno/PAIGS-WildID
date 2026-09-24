"""Configuration subsystem -- service-layer tests (seeding, list, update,
effective-threshold resolution, and the stage-kwargs mapping), against a
raw DB session (db_session fixture) rather than the HTTP API -- that's
covered separately in test_api_config.py.
"""
import pytest

from app.configuration import service as config_service
from app.configuration.catalog import CATALOG
from app.configuration.errors import (
    ConfigNotFoundError,
    ConfigValueOutOfBoundsError,
    UnknownConfigKeyError,
)
from app.models.config import ConfigThreshold


class TestEnsureSeeded:
    def test_seeds_one_row_per_catalog_key_with_its_default_value(self, db_session):
        config_service.ensure_seeded(db_session)
        rows = db_session.query(ConfigThreshold).all()
        assert len(rows) == len(CATALOG)
        by_key = {row.key: row.value for row in rows}
        for definition in CATALOG:
            assert by_key[definition.key] == definition.default

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


class TestValidateOverrides:
    def test_accepts_known_keys_within_bounds(self):
        config_service.validate_overrides({"usability_check.min_length": 400})

    def test_rejects_unknown_key(self):
        with pytest.raises(UnknownConfigKeyError):
            config_service.validate_overrides({"not_a_real_stage.not_a_real_param": 1})

    def test_rejects_out_of_bounds_value(self):
        with pytest.raises(ConfigValueOutOfBoundsError):
            config_service.validate_overrides({"orientation.min_identity": 2.0})


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
