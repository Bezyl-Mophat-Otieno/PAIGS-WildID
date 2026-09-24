"""Stage 8 (FASTA generation) tests.

Written first, against the not-yet-existing app.pipeline.fasta module,
to confirm red before implementing.

Per CLAUDE.md: a pure format-conversion step using Biopython's
Bio.SeqIO to write Stage 7's usable sequence out as FASTA -- the
standard text format Stage 9's BLAST search (and nearly every other
bioinformatics tool) expects as input. The header is the sample ID,
e.g. `>WILD_001`.
"""
import io

import pytest
from Bio import SeqIO

from app.pipeline.fasta import generate_fasta, write_fasta_file


class TestGenerateFasta:
    def test_header_uses_sample_id(self):
        result = generate_fasta("WILD_001", "ATCGATCG")

        assert result.fasta_content.startswith(">WILD_001\n")

    def test_records_sequence_length(self):
        result = generate_fasta("WILD_001", "ATCG" * 20)

        assert result.sequence_length == 80

    def test_sequence_id_is_sample_id(self):
        result = generate_fasta("WILD_042", "ATCG")

        assert result.sequence_id == "WILD_042"

    def test_wraps_long_sequences_at_60_characters_per_line(self):
        sequence = "ATCG" * 20  # 80bp -> two lines: 60 + 20
        result = generate_fasta("WILD_001", sequence)

        lines = result.fasta_content.strip("\n").splitlines()
        assert lines[0] == ">WILD_001"
        assert lines[1] == sequence[:60]
        assert lines[2] == sequence[60:]

    def test_round_trips_through_biopython_parser(self):
        sequence = "ACGTACGTAC" * 10
        result = generate_fasta("WILD_007", sequence)

        parsed = list(SeqIO.parse(io.StringIO(result.fasta_content), "fasta"))

        assert len(parsed) == 1
        assert parsed[0].id == "WILD_007"
        assert str(parsed[0].seq) == sequence

    def test_rejects_empty_sequence(self):
        with pytest.raises(ValueError):
            generate_fasta("WILD_001", "")


class TestWriteFastaFile:
    """
    The Stage 8 -> Stage 9 handoff named in claude/stage-8-9-status.md's
    Known follow-ups: generate_fasta() only ever produced an in-memory
    string, but search_blast() needs a real file path (blastn is a
    subprocess, it reads files, not Python strings). This is the missing
    half of that gap -- the other half (looking up which reference
    database to search against) is
    app.reference.publish.search_active_reference_database().
    """

    def test_writes_the_exact_fasta_content(self, tmp_path):
        result = generate_fasta("WILD_001", "ATCG" * 20)
        dest = tmp_path / "query.fasta"

        written_path = write_fasta_file(result, dest)

        assert written_path == dest
        assert dest.read_text() == result.fasta_content

    def test_creates_missing_parent_directories(self, tmp_path):
        result = generate_fasta("WILD_001", "ATCG" * 20)
        dest = tmp_path / "runs" / "some-run-id" / "query.fasta"

        write_fasta_file(result, dest)

        assert dest.is_file()

    def test_written_file_round_trips_through_biopython(self, tmp_path):
        sequence = "ACGTACGTAC" * 10
        result = generate_fasta("WILD_007", sequence)
        dest = tmp_path / "query.fasta"

        write_fasta_file(result, dest)
        parsed = list(SeqIO.parse(str(dest), "fasta"))

        assert len(parsed) == 1
        assert parsed[0].id == "WILD_007"
        assert str(parsed[0].seq) == sequence
