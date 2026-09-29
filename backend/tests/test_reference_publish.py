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
from app.pipeline.blast import RemoteBlastSearchError, search_blast
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

    # mode="local" is passed explicitly throughout most of this class:
    # blast.mode's own catalog default is now "remote" (see
    # app.configuration.catalog) -- the remote-vs-local BLAST search
    # decision -- so leaving mode unspecified would exercise the remote
    # path instead of the local one most of these tests are actually
    # about. The remote path itself is covered by TestSearchActiveReferenceDatabaseRemoteMode
    # below, with subprocess mocked the same way _mock_makeblastdb does
    # for publishing (no real network call, no dependency on NCBI being
    # reachable from wherever these tests run).

    def test_raises_when_nothing_has_been_published_yet(self, tmp_path, db_session):
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        with pytest.raises(NoActiveReferenceDatabaseError):
            search_active_reference_database(query, db_session, mode="local")

    def test_searches_against_the_active_version(self, tmp_path, db_session):
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session, mode="local")

        assert result.database_version == "v1"
        assert result.hits[0].accession == "SYNTH001"
        assert result.hits[0].identity == pytest.approx(100.0)
        assert result.search_mode == "local"

    def test_uses_whichever_version_is_currently_active(self, tmp_path, db_session):
        root = tmp_path / "reference_data"
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(fasta, "v1", db=db_session, reference_data_root=root)
        publish_reference_db(fasta, "v2", db=db_session, reference_data_root=root)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session, mode="local")

        assert result.database_version == "v2"

    def test_respects_max_hits(self, tmp_path, db_session):
        fasta = _write_fasta(tmp_path, "reference_v1.fasta", SYNTHETIC_FASTA)
        publish_reference_db(
            fasta, "v1", db=db_session, reference_data_root=tmp_path / "reference_data"
        )
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session, max_hits=1, mode="local")

        assert len(result.hits) <= 1


FAKE_REMOTE_STDOUT = "SYNTH001\t99.71\t138\t0.0\t250.0\tSYNTH001 Panthera leo\n"


def _mock_remote_blastn(monkeypatch, *, stdout=FAKE_REMOTE_STDOUT, returncode=0, stderr=""):
    """Mocks the subprocess boundary in app.pipeline.blast, same technique
    _mock_makeblastdb uses above -- a real network round trip to NCBI has
    no place in a unit test (slow, non-deterministic, requires the test
    runner to have internet access at all). Also stubs binary discovery
    (app.pipeline.blast.shutil.which, the same seam test_blast.py's own
    TestFindBlastBinary tests use) so these tests pass regardless of
    whether a real blastn binary happens to be installed wherever they
    run -- unlike test_blast.py's own tests, which deliberately exercise
    the real binaries. Returns the list of commands actually invoked, so
    a test can assert on the exact blastn flags."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("app.pipeline.blast.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("app.pipeline.blast.subprocess.run", fake_run)
    return calls


class TestSearchActiveReferenceDatabaseRemoteMode:
    """mode="remote" (blast.mode's own catalog default): no reference DB
    lookup at all -- dispatches straight to search_blast_remote(), which
    never touches get_active_version()/ReferenceDatabaseVersion."""

    def test_default_mode_dispatches_to_remote_search(self, db_session, monkeypatch):
        calls = _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session)

        assert result.search_mode == "remote"
        assert result.hits[0].species == "Panthera leo"
        assert len(calls) == 1

    def test_builds_the_remote_blastn_command_with_no_local_db_prefix(
        self, db_session, monkeypatch
    ):
        calls = _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        search_active_reference_database(query, db_session, remote_database="refseq_rna")

        cmd = calls[0]["cmd"]
        assert "-remote" in cmd
        assert "-db" in cmd
        assert cmd[cmd.index("-db") + 1] == "refseq_rna"

    def test_entrez_query_is_passed_through_when_given(self, db_session, monkeypatch):
        calls = _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        search_active_reference_database(
            query, db_session, entrez_query="Chordata[Organism]"
        )

        cmd = calls[0]["cmd"]
        assert "-entrez_query" in cmd
        assert cmd[cmd.index("-entrez_query") + 1] == "Chordata[Organism]"

    def test_entrez_query_omitted_when_blank(self, db_session, monkeypatch):
        calls = _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        search_active_reference_database(query, db_session, entrez_query="")

        assert "-entrez_query" not in calls[0]["cmd"]

    def test_result_records_remote_evidence_for_the_audit_trail(self, db_session, monkeypatch):
        _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(
            query, db_session, remote_database="nt", entrez_query="Chordata[Organism]"
        )

        assert result.remote_database == "nt"
        assert result.entrez_query == "Chordata[Organism]"
        assert result.queried_at is not None
        assert result.raw_response == FAKE_REMOTE_STDOUT
        assert "not version-pinned" in result.database_version

    def test_raises_remote_blast_search_error_on_nonzero_exit(self, db_session, monkeypatch):
        _mock_remote_blastn(monkeypatch, returncode=1, stderr="NCBI rejected the request")
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        with pytest.raises(RemoteBlastSearchError, match="NCBI rejected the request"):
            search_active_reference_database(query, db_session)

    def test_raises_remote_blast_search_error_on_timeout(self, db_session, monkeypatch):
        import subprocess

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

        monkeypatch.setattr("app.pipeline.blast.shutil.which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr("app.pipeline.blast.subprocess.run", fake_run)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        with pytest.raises(RemoteBlastSearchError, match="timed out"):
            search_active_reference_database(query, db_session, remote_timeout_seconds=5)

    def test_never_looks_up_a_local_reference_database_version(self, db_session, monkeypatch):
        """No reference DB has ever been published in this test (unlike
        the local-mode tests above), yet the remote path must still
        succeed -- proof it never calls get_active_version()."""
        _mock_remote_blastn(monkeypatch)
        query = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"

        result = search_active_reference_database(query, db_session)

        assert result.search_mode == "remote"
