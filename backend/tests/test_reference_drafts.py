"""app.reference.drafts -- the human review/approve workflow sitting
between app.reference.bold's automated fetch and the existing, unchanged
publish_reference_db(). fetch_bold_taxon itself is mocked here (no real
network call) -- see tests/test_bold.py for that module's own coverage;
these tests are about the draft workflow (create/list/get/publish/
discard), not BOLD's response parsing again.
"""
from pathlib import Path

import pytest

from app.reference.bold import BoldFetchResult, BoldSpeciesSummary
from app.reference.drafts import (
    DraftNotFoundError,
    DraftNotPendingError,
    create_draft,
    discard_draft,
    get_draft,
    list_drafts,
    publish_draft,
)
from app.models.reference import ReferenceDatabaseDraft


def _fake_fetch_result(taxon="Panthera"):
    return BoldFetchResult(
        taxon=taxon,
        marker="COI-5P",
        fasta_content=">AAA001-01 Panthera leo | Animalia;Chordata;Mammalia;Carnivora;Felidae;Panthera;Panthera leo\n"
        + "ACGT" * 100
        + "\n",
        species=[
            BoldSpeciesSummary(
                species="Panthera leo", kept_count=1, dropped_count=0, bins=["BOLD:AAA0001"]
            )
        ],
        total_fetched=1,
        total_kept=1,
        drop_reasons={},
        species_sharing_a_bin=[],
    )


class TestCreateDraft:
    def test_creates_a_pending_review_draft_with_a_written_fasta_file(
        self, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )

        draft = create_draft(
            "Panthera", db_session, requested_by="user-1", reference_data_root=tmp_path
        )

        assert draft.status == "pending_review"
        assert draft.source == "bold"
        assert draft.taxon == "Panthera"
        assert draft.requested_by == "user-1"
        assert draft.published_as_version is None
        assert Path(draft.fasta_path).is_file()
        assert "Panthera leo" in Path(draft.fasta_path).read_text()

    def test_summary_carries_species_counts_and_bin_flags(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )

        draft = create_draft("Panthera", db_session, reference_data_root=tmp_path)

        assert draft.summary["total_kept"] == 1
        assert draft.summary["species"][0]["species"] == "Panthera leo"
        assert draft.summary["species"][0]["bin_consistent"] is True

    def test_passes_optional_kwargs_through_to_fetch(self, db_session, tmp_path, monkeypatch):
        """create_draft resolves the full bold_fetch.* config slice (global
        defaults, with any explicitly-passed values overridden) via the
        same Configuration subsystem every Run stage's thresholds use --
        so fetch_bold_taxon always receives all four filtering kwargs,
        not just whichever ones this call happened to override."""
        captured = {}

        def _fake_fetch(taxon, **kwargs):
            captured["taxon"] = taxon
            captured.update(kwargs)
            return _fake_fetch_result(taxon)

        monkeypatch.setattr("app.reference.drafts.fetch_bold_taxon", _fake_fetch)

        create_draft(
            "Felidae",
            db_session,
            marker="COI-3P",
            max_records_per_species=3,
            reference_data_root=tmp_path,
        )

        assert captured["taxon"] == "Felidae"
        assert captured["marker"] == "COI-3P"
        assert captured["max_records_per_species"] == 3
        # Left at the global default -- not overridden by this call.
        assert captured["min_sequence_length"] == 200
        assert captured["max_n_proportion"] == 0.05
        assert captured["require_species_level"] == "required"

    def test_overriding_require_species_level_and_quality_floor(
        self, db_session, tmp_path, monkeypatch
    ):
        captured = {}

        def _fake_fetch(taxon, **kwargs):
            captured.update(kwargs)
            return _fake_fetch_result(taxon)

        monkeypatch.setattr("app.reference.drafts.fetch_bold_taxon", _fake_fetch)

        create_draft(
            "Felidae",
            db_session,
            min_sequence_length=100,
            max_n_proportion=0.1,
            require_species_level="allow_lower_rank",
            reference_data_root=tmp_path,
        )

        assert captured["min_sequence_length"] == 100
        assert captured["max_n_proportion"] == 0.1
        assert captured["require_species_level"] == "allow_lower_rank"

    def test_rejects_an_invalid_require_species_level_value(self, db_session, tmp_path, monkeypatch):
        from app.configuration.errors import ConfigValueNotAllowedError

        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )

        with pytest.raises(ConfigValueNotAllowedError):
            create_draft(
                "Felidae",
                db_session,
                require_species_level="not_a_real_choice",
                reference_data_root=tmp_path,
            )

    def test_rejects_an_out_of_bounds_max_n_proportion(self, db_session, tmp_path, monkeypatch):
        from app.configuration.errors import ConfigValueOutOfBoundsError

        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )

        with pytest.raises(ConfigValueOutOfBoundsError):
            create_draft("Felidae", db_session, max_n_proportion=5.0, reference_data_root=tmp_path)


class TestListAndGetDrafts:
    def test_list_drafts_returns_newest_first(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        first = create_draft("Panthera", db_session, reference_data_root=tmp_path)
        second = create_draft("Felidae", db_session, reference_data_root=tmp_path)

        rows = list_drafts(db_session)

        assert [r.id for r in rows][:2] == [second.id, first.id]

    def test_get_draft_raises_for_unknown_id(self, db_session):
        with pytest.raises(DraftNotFoundError):
            get_draft("does-not-exist", db_session)


class TestPublishDraft:
    def test_publishing_calls_the_real_publish_path_and_marks_the_draft_published(
        self, db_session, tmp_path, temp_reference_data_root, monkeypatch
    ):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        draft = create_draft("Panthera", db_session, reference_data_root=tmp_path)

        result = publish_draft(draft.id, "bold-panthera-v1", db_session)

        assert result.version == "bold-panthera-v1"
        refreshed = get_draft(draft.id, db_session)
        assert refreshed.status == "published"
        assert refreshed.published_as_version == "bold-panthera-v1"
        assert refreshed.reviewed_at is not None

    def test_raises_for_unknown_draft(self, db_session):
        with pytest.raises(DraftNotFoundError):
            publish_draft("does-not-exist", "v1", db_session)

    def test_raises_if_already_published(self, db_session, tmp_path, temp_reference_data_root, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        draft = create_draft("Panthera", db_session, reference_data_root=tmp_path)
        publish_draft(draft.id, "bold-panthera-v1", db_session)

        with pytest.raises(DraftNotPendingError):
            publish_draft(draft.id, "bold-panthera-v2", db_session)


class TestDiscardDraft:
    def test_discarding_marks_the_draft_discarded_without_publishing_anything(
        self, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        draft = create_draft("Panthera", db_session, reference_data_root=tmp_path)

        discarded = discard_draft(draft.id, db_session)

        assert discarded.status == "discarded"
        assert discarded.published_as_version is None
        assert (
            db_session.query(ReferenceDatabaseDraft).filter_by(id=draft.id).one().status
            == "discarded"
        )

    def test_raises_if_already_discarded(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        draft = create_draft("Panthera", db_session, reference_data_root=tmp_path)
        discard_draft(draft.id, db_session)

        with pytest.raises(DraftNotPendingError):
            discard_draft(draft.id, db_session)
