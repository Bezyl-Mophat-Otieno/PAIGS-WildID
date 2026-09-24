"""Stage 9 (BLAST comparison) tests.

Written first, against the not-yet-existing app.pipeline.blast module,
to confirm red before implementing.

Per CLAUDE.md: Stage 8's FASTA is searched against a curated reference
database of known species via BLAST+ (a separate compiled binary,
invoked here as a subprocess -- not a pip-installable package). The
reference database itself is a domain-expert deliverable, built ahead
of time from real curated species data; engineering does not invent it.
The fixture used here, tests/fixtures/synthetic_blast_reference.fasta,
is instead a small, obviously-synthetic placeholder (fake accession
numbers prefixed "SYNTH", made-up sequences attached to real big-cat
species names purely for readability) that exists to prove the
makeblastdb/blastn plumbing works end-to-end. It is a stand-in for
testing only, never real reference data -- that is to be supplied by
domain experts and swapped in later (see claude/stage-8-9-status.md).

These tests exercise the real BLAST+ binaries directly (no mocking of
blastn/makeblastdb) -- BLAST+ is installed in this dev environment via
the no-root technique documented in claude/stage-8-9-status.md, and the
project's Dockerfile installs it normally (`apt-get install
ncbi-blast+`, root available) for deployment.
"""
from pathlib import Path

import pytest

from app.pipeline.blast import (
    DEFAULT_MAX_HITS,
    _find_blast_binary,
    build_reference_database,
    search_blast,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REFERENCE_FASTA = FIXTURES_DIR / "synthetic_blast_reference.fasta"
QUERY_EXACT_MATCH = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"
QUERY_NO_HITS = FIXTURES_DIR / "synthetic_blast_query_no_hits.fasta"


class TestFindBlastBinary:
    def test_env_var_override_takes_precedence(self, tmp_path, monkeypatch):
        fake_bin = tmp_path / "blastn"
        fake_bin.write_text("#!/bin/sh\n")
        fake_bin.chmod(0o755)
        monkeypatch.setenv("BLAST_BIN_DIR", str(tmp_path))

        assert _find_blast_binary("blastn") == str(fake_bin)

    def test_env_var_set_but_binary_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BLAST_BIN_DIR", str(tmp_path))

        with pytest.raises(RuntimeError, match="BLAST_BIN_DIR"):
            _find_blast_binary("blastn")

    def test_falls_back_to_path_when_no_env_var(self, monkeypatch):
        monkeypatch.delenv("BLAST_BIN_DIR", raising=False)
        monkeypatch.setattr(
            "app.pipeline.blast.shutil.which", lambda name: f"/usr/bin/{name}"
        )

        assert _find_blast_binary("blastn") == "/usr/bin/blastn"

    def test_falls_back_to_home_ncbi_blast_dir_when_not_on_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BLAST_BIN_DIR", raising=False)
        monkeypatch.setattr("app.pipeline.blast.shutil.which", lambda name: None)
        fake_home_bin = tmp_path / "ncbi-blast+" / "bin"
        fake_home_bin.mkdir(parents=True)
        (fake_home_bin / "blastn").write_text("#!/bin/sh\n")
        monkeypatch.setattr("app.pipeline.blast.Path.home", lambda: tmp_path)

        assert _find_blast_binary("blastn") == str(fake_home_bin / "blastn")

    def test_raises_when_binary_found_nowhere(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BLAST_BIN_DIR", raising=False)
        monkeypatch.setattr("app.pipeline.blast.shutil.which", lambda name: None)
        monkeypatch.setattr("app.pipeline.blast.Path.home", lambda: tmp_path)

        with pytest.raises(RuntimeError, match="Could not locate"):
            _find_blast_binary("blastn")


class TestBuildReferenceDatabase:
    def test_raises_on_malformed_reference_fasta(self, tmp_path):
        bad_fasta = tmp_path / "bad.fasta"
        bad_fasta.write_text("this is not a fasta file at all, no header line\n")

        with pytest.raises(RuntimeError):
            build_reference_database(bad_fasta, tmp_path / "baddb", title="bad")


class TestSearchBlast:
    @pytest.fixture()
    def reference_db(self, tmp_path):
        db_prefix = tmp_path / "refdb"
        build_reference_database(REFERENCE_FASTA, db_prefix, title="synthetic smoke-test DB")
        return db_prefix

    def test_top_hit_is_the_exact_match(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        assert result.hits[0].accession == "SYNTH001"
        assert result.hits[0].identity == pytest.approx(100.0)
        assert result.hits[0].rank == 1

    def test_hits_are_ranked_best_first(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        bit_scores = [hit.bit_score for hit in result.hits]
        assert bit_scores == sorted(bit_scores, reverse=True)
        assert [hit.rank for hit in result.hits] == list(range(1, len(result.hits) + 1))

    def test_finds_related_but_lower_identity_hits_too(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        accessions = {hit.accession for hit in result.hits}
        assert "SYNTH002" in accessions
        second = next(h for h in result.hits if h.accession == "SYNTH002")
        assert result.hits[0].identity > second.identity

    def test_species_name_is_parsed_from_subject_title(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        assert result.hits[0].species == "Panthera leo"

    def test_coverage_is_computed_against_query_length(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        assert result.query_length == 138
        for hit in result.hits:
            assert 0 < hit.coverage <= 100.0

    def test_records_the_supplied_database_version(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        assert result.database_version == "synthetic-v0-test"

    def test_returns_no_hits_for_an_unrelated_query(self, reference_db):
        result = search_blast(QUERY_NO_HITS, reference_db, database_version="synthetic-v0-test")

        assert result.hits == []
        assert result.query_length == 150

    def test_respects_max_hits(self, reference_db):
        result = search_blast(
            QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test", max_hits=1
        )

        assert len(result.hits) <= 1

    def test_default_max_hits_used_when_not_specified(self, reference_db):
        result = search_blast(QUERY_EXACT_MATCH, reference_db, database_version="synthetic-v0-test")

        assert len(result.hits) <= DEFAULT_MAX_HITS

    def test_raises_on_empty_query_fasta(self, tmp_path, reference_db):
        empty_query = tmp_path / "empty.fasta"
        empty_query.write_text("")

        with pytest.raises(ValueError):
            search_blast(empty_query, reference_db, database_version="synthetic-v0-test")

    def test_raises_when_database_does_not_exist(self, tmp_path):
        with pytest.raises(RuntimeError):
            search_blast(
                QUERY_EXACT_MATCH,
                tmp_path / "nonexistent_db",
                database_version="synthetic-v0-test",
            )
