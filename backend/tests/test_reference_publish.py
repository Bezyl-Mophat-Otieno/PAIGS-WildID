"""
Reference Database Setup (Part A) tests.

Written first, against the not-yet-existing app.reference.publish module,
to confirm red before implementing.

Covers: FASTA validation (rejects malformed/empty input before ever
touching makeblastdb, same "parse attempt is the check" philosophy as
Stage 1's format check), correct delegation to makeblastdb (mocked at the
subprocess boundary, per the brief's explicit instruction -- unlike
app/pipeline/blast.py's own tests, which deliberately run the real
binaries), correct ReferenceEntry population from FASTA headers, correct
active-version bookkeeping, and one real, unmocked integration test that
publishes against the actual BLAST+ binaries and confirms the resulting
index is genuinely searchable.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.reference import ReferenceDatabaseVersion, ReferenceEntry
from app.pipeline.blast import search_blast
from app.reference.publish import (
    InvalidReferenceFastaError,
    NoActiveReferenceDatabaseError,
    get_active_version,
    publish_reference_db,
    search_active_reference_database,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SYNTHETIC_FASTA = """\
>SYNTH001 Panthera leo | Felidae
ATGGCCAACGTACTAGTAATGATCGGAGGATTTGGAAACTGACTAGTGCCTCTAATAATCGGGGCCCCA
GACATAGCATTTCCACGAATAAATAATATAAGCTTCTGACTTCTCCCTCCTTCTTTCCTATTACTCCTA
>SYNTH002 Panthera pardus
ATGGCCAACGTACTAGTAATGATCGGAGGATTTGGCAACTGACTAGTGCCTCTAATAATCGGGGCCCCT
GACATAGCATTTCCACGAATAAATAATATAAGCTTCTGACTTCTCCCTCCTTCTTTCCTATTACTCCTG
"""


def _write_fasta(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def _mock_makeblastdb(monkeypatch):
    """
    Mock the subprocess boundary in app.pipeline.blast, per the brief's
    explicit instruction for this module's unit tests -- build_reference_database
    still runs for real up to the actual subprocess call (real binary
    resolution, real directory creation), just without really invoking
    makeblastdb, so these tests stay fast and don't depend on real index
    files being produced.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.pipeline.blast.subprocess.run", fake_run)
    return calls


class TestValidatesFastaBeforePublishing:
    def test_rejects_malformed_fasta(self, tmp_path, db_session):
        bad = _write_fasta(tmp_path, "bad.fasta", "this is not a fasta file at all\n")

        with pytest.raises(InvalidReferenceFastaError):
            publish_reference_db(
                bad, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
            )

    def test_rejects_empty_fasta(self, tmp_path, db_session):
        empty = _write_fasta(tmp_path, "empty.fasta", "")

        with pytest.raises(InvalidReferenceFastaError):
            publish_reference_db(
                empty, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
            )

    def test_rejects_a_record_with_an_empty_sequence(self, tmp_path, db_session):
        bad = _write_fasta(tmp_path, "bad.fasta", ">SYNTH001 Panthera leo\n\n")

        with pytest.raises(InvalidReferenceFastaError):
            publish_reference_db(
                bad, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
            )

    def test_never_calls_makeblastdb_on_invalid_input(self, tmp_path, db_session, monkeypatch):
        calls = _mock_makeblastdb(monkeypatch)
        bad = _write_fasta(tmp_path, "bad.fasta", "not fasta\n")

        with pytest.raises(InvalidReferenceFastaError):
            publish_reference_db(
                bad, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
            )

        assert calls == []


class TestCallsMakeblastdbWithCorrectArguments:
    def test_delegates_with_the_right_fasta_and_output_paths(self, tmp_path, db_session, monkeypatch):
        calls = _mock_makeblastdb(monkeypatch)
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        root = tmp_path / "reference_data"

        result = publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)

        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[0].endswith("makeblastdb")
        assert cmd[cmd.index("-in") + 1] == str(root / "v1" / "reference.fasta")
        assert cmd[cmd.index("-dbtype") + 1] == "nucl"
        assert cmd[cmd.index("-out") + 1] == result.db_prefix

    def test_copies_the_source_fasta_to_its_canonical_location(self, tmp_path, db_session, monkeypatch):
        _mock_makeblastdb(monkeypatch)
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        root = tmp_path / "reference_data"

        result = publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)

        canonical = Path(result.fasta_path)
        assert canonical.is_file()
        assert canonical.read_text() == SYNTHETIC_FASTA
        assert canonical != fasta  # copied, not the original path


class TestParsesReferenceEntries:
    def test_populates_one_entry_per_species(self, tmp_path, db_session, monkeypatch):
        _mock_makeblastdb(monkeypatch)
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)

        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )

        entries = (
            db_session.query(ReferenceEntry)
            .filter_by(version="v1")
            .order_by(ReferenceEntry.accession)
            .all()
        )
        assert [e.accession for e in entries] == ["SYNTH001", "SYNTH002"]
        assert entries[0].species == "Panthera leo"
        assert entries[0].taxonomy == "Felidae"
        assert entries[1].species == "Panthera pardus"
        assert entries[1].taxonomy is None
        assert all(e.source == "reference_v1.fasta" for e in entries)
        assert all(e.version == "v1" for e in entries)

    def test_republishing_same_version_replaces_its_entries(self, tmp_path, db_session, monkeypatch):
        _mock_makeblastdb(monkeypatch)
        root = tmp_path / "reference_data"
        fasta_v1 = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(fasta_v1, "v1", db=db_session, reference_data_root=root)

        one_species_only = SYNTHETIC_FASTA.split(">SYNTH002")[0]
        smaller_fasta = _write_fasta(tmp_path, "reference_v1b.fasta", one_species_only)
        publish_reference_db(smaller_fasta, "v1", db=db_session, reference_data_root=root)

        entries = db_session.query(ReferenceEntry).filter_by(version="v1").all()
        assert len(entries) == 1
        assert entries[0].accession == "SYNTH001"


class TestActiveVersionPointer:
    def test_first_publish_becomes_active(self, tmp_path, db_session, monkeypatch):
        _mock_makeblastdb(monkeypatch)
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)

        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )

        active = get_active_version(db_session)
        assert active is not None
        assert active.version == "v1"
        assert active.sequence_count == 2

    def test_publishing_a_new_version_deactivates_the_old_one(self, tmp_path, db_session, monkeypatch):
        _mock_makeblastdb(monkeypatch)
        root = tmp_path / "reference_data"
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)
        publish_reference_db(fasta, "v2", db=db_session, reference_data_root=root)

        versions = {
            v.version: v.is_active
            for v in db_session.query(ReferenceDatabaseVersion).all()
        }
        assert versions == {"v1": False, "v2": True}

    def test_old_versions_entries_stay_intact_after_a_new_one_is_active(
        self, tmp_path, db_session, monkeypatch
    ):
        _mock_makeblastdb(monkeypatch)
        root = tmp_path / "reference_data"
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)
        publish_reference_db(fasta, "v2", db=db_session, reference_data_root=root)

        v1_entries = db_session.query(ReferenceEntry).filter_by(version="v1").all()
        assert len(v1_entries) == 2

    def test_no_active_version_before_anything_is_published(self, db_session):
        assert get_active_version(db_session) is None


class TestRealIntegration:
    """
    Unmocked: runs the real makeblastdb/blastn binaries. This is the
    integration test the brief calls for -- it produces a real, searchable
    fixture index, proving the whole publish -> search path actually works
    end to end, not just that the right subprocess arguments were built.
    """

    def test_published_index_is_actually_searchable(self, tmp_path, db_session):
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)

        result = publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )

        assert Path(result.fasta_path).is_file()
        for ext in (".nhr", ".nin", ".nsq"):
            assert Path(result.db_prefix + ext).is_file(), f"missing {ext} index file"

        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"
        search_result = search_blast(
            query, Path(result.db_prefix), database_version=result.version
        )

        assert search_result.hits[0].accession == "SYNTH001"
        assert search_result.hits[0].identity == pytest.approx(100.0)
        assert search_result.database_version == "v1"


class TestSearchActiveReferenceDatabase:
    """
    The other half of the Stage 8 -> Stage 9 handoff named in
    claude/stage-8-9-status.md's Known follow-ups: nothing called
    get_active_version() and threaded its db_prefix/version into
    search_blast(). This is that missing glue -- the FASTA-file half
    lives in app.pipeline.fasta.write_fasta_file(), tested separately in
    tests/test_fasta.py.
    """

    def test_raises_when_nothing_has_been_published_yet(self, tmp_path, db_session):
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        with pytest.raises(NoActiveReferenceDatabaseError):
            search_active_reference_database(query, db_session)

    def test_searches_against_the_active_version(self, tmp_path, db_session):
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session)

        assert result.database_version == "v1"
        assert result.hits[0].accession == "SYNTH001"
        assert result.hits[0].identity == pytest.approx(100.0)

    def test_uses_whichever_version_is_currently_active(self, tmp_path, db_session):
        root = tmp_path / "reference_data"
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)
        publish_reference_db(fasta, "v2", db=db_session, reference_data_root=root)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session)

        assert result.database_version == "v2"

    def test_respects_max_hits(self, tmp_path, db_session):
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session, max_hits=1)

        assert len(result.hits) <= 1
