"""Stage 11 (Reporting) tests.

Written first, against the not-yet-existing app.pipeline.report module,
to confirm red before implementing.

Per CLAUDE.md: "every prior stage's data is assembled into one auditable
report" -- Reporting doesn't compute anything new, it renders what every
earlier stage already produced (ReportInput just aggregates their
already-existing typed outputs) into one PDF via ReportLab (already the
pinned dependency in requirements.txt).

pypdf is used here, test-only, to extract real text back out of the
generated PDF and assert on it -- so these tests check the report
actually *says* the right thing, not just that PDF bytes came out the
other end.
"""
import io
from datetime import datetime, timezone

from pypdf import PdfReader

from app.pipeline.report import DEFAULT_LIMITATION, generate_report, write_report_file
from app.schemas.blast import BlastHit, BlastSearchResult
from app.schemas.consensus import ConsensusResult
from app.schemas.fasta import FastaResult
from app.schemas.format_check import FileFormatCheck
from app.schemas.identification import IdentificationResult
from app.schemas.orientation import OrientationResult
from app.schemas.ab1_extraction import ReadExtraction
from app.schemas.report import ReportInput
from app.schemas.sanity_check import SanityCheckResult
from app.schemas.trim import TrimResult
from app.schemas.usability_check import UsabilityCheckResult


def _hit(rank, species, identity, coverage, accession="REFXXX", evalue=0.0, bit_score=1000.0):
    return BlastHit(
        rank=rank,
        species=species,
        identity=identity,
        coverage=coverage,
        evalue=evalue,
        bit_score=bit_score,
        accession=accession,
    )


def _quality_scores(length, seed):
    """Deterministic pseudo-Phred trace (values 10-60) -- no real RNG
    needed, just something with a non-trivial min/mean/max that a test
    can recompute identically from the same (length, seed)."""
    return [10 + ((i * seed * 7 + seed) % 51) for i in range(length)]


def _base_report_input(**overrides):
    defaults = dict(
        run_id="run-123",
        sample_id="WILD_001",
        original_filenames=["fwd.ab1", "rev.ab1"],
        generated_at=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
        format_check={
            "forward": FileFormatCheck(filename="fwd.ab1", valid=True),
            "reverse": FileFormatCheck(filename="rev.ab1", valid=True),
        },
        sanity_check={
            "forward": SanityCheckResult(n_proportion=0.0, raw_length=795, status="PASS"),
            "reverse": SanityCheckResult(n_proportion=0.0, raw_length=1165, status="PASS"),
        },
        trim={
            "forward": TrimResult(
                trimmed_sequence="A" * 667,
                trimmed_length=667,
                trim_start=29,
                trim_end=696,
                trim_params={"quality_threshold": 20, "min_window_size": 50},
            ),
            "reverse": TrimResult(
                trimmed_sequence="A" * 1073,
                trimmed_length=1073,
                trim_start=15,
                trim_end=1088,
                trim_params={"quality_threshold": 20, "min_window_size": 50},
            ),
        },
        ab1_extraction={
            "forward": ReadExtraction(
                raw_sequence="A" * 795,
                raw_length=795,
                quality_scores=_quality_scores(795, seed=1),
            ),
            "reverse": ReadExtraction(
                raw_sequence="A" * 1165,
                raw_length=1165,
                quality_scores=_quality_scores(1165, seed=2),
            ),
        },
        orientation=OrientationResult(
            orientation="reverse_read_reverse_complemented",
            alignment_score=60.0,
            overlap_length=60,
            identity=1.0,
            label_orientation_mismatch=False,
        ),
        consensus=ConsensusResult(
            consensus_sequence="A" * 680,
            consensus_length=680,
            ambiguous_positions=[],
            quality_scores=[40] * 680,
        ),
        usability_check=UsabilityCheckResult(
            final_length=680, mean_quality=45.2, ambiguous_positions=0, status="PASS"
        ),
        fasta=FastaResult(
            sequence_id="WILD_001", sequence_length=680, fasta_content=">WILD_001\n" + "A" * 680
        ),
        blast=BlastSearchResult(
            hits=[
                _hit(1, "Panthera leo", 99.71, 98.2),
                _hit(2, "Panthera pardus", 91.0, 95.0),
            ],
            database_version="v3",
            query_length=680,
        ),
        identification=IdentificationResult(
            candidate_species="Panthera leo",
            identity=99.71,
            coverage=98.2,
            status="PASS",
            thresholds_applied={
                "min_identity_pct": 98.0,
                "min_coverage_pct": 90.0,
                "ambiguous_margin_pct": 1.0,
            },
        ),
    )
    defaults.update(overrides)
    return ReportInput(**defaults)


def _extract_text(pdf_bytes: bytes) -> str:
    """Extracted text, whitespace-normalized. ReportLab wraps a
    Paragraph's text at the page width, and pypdf's extraction preserves
    those visual line breaks as literal newlines -- normalizing here
    keeps assertions about *content* from being fragile to exactly where
    a sentence happens to wrap."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(page.extract_text() for page in reader.pages)
    return " ".join(raw.split())


class TestGenerateReport:
    def test_produces_valid_pdf_bytes(self):
        pdf_bytes = generate_report(_base_report_input())

        assert pdf_bytes.startswith(b"%PDF")

    def test_contains_run_and_sample_identifiers(self):
        text = _extract_text(generate_report(_base_report_input()))

        assert "run-123" in text
        assert "WILD_001" in text

    def test_contains_final_identification_status_and_species(self):
        text = _extract_text(generate_report(_base_report_input()))

        assert "PASS" in text
        assert "Panthera leo" in text
        assert "99.71" in text

    def test_lists_every_blast_hit_species(self):
        text = _extract_text(generate_report(_base_report_input()))

        assert "Panthera leo" in text
        assert "Panthera pardus" in text

    def test_reports_review_required_with_reason(self):
        report_input = _base_report_input(
            identification=IdentificationResult(
                candidate_species="Panthera leo",
                identity=91.0,
                coverage=98.2,
                status="REVIEW REQUIRED",
                reason="Top match identity 91.00% is below the minimum of 98.0%.",
                thresholds_applied={
                    "min_identity_pct": 98.0,
                    "min_coverage_pct": 90.0,
                    "ambiguous_margin_pct": 1.0,
                },
            )
        )

        text = _extract_text(generate_report(report_input))

        assert "REVIEW REQUIRED" in text
        assert "below the minimum of 98.0%" in text

    def test_always_flags_taxonomic_consistency_not_checked(self):
        # IdentificationResult.taxonomic_consistency_checked defaults to False --
        # this must surface in every report, not just ones that set it explicitly.
        text = _extract_text(generate_report(_base_report_input()))

        assert "taxonomic consistency" in text.lower()

    def test_includes_label_orientation_mismatch_note_when_true(self):
        report_input = _base_report_input(
            orientation=OrientationResult(
                orientation="as_is",
                alignment_score=60.0,
                overlap_length=60,
                identity=1.0,
                label_orientation_mismatch=True,
            )
        )

        text = _extract_text(generate_report(report_input))

        assert "mismatch" in text.lower()

    def test_single_read_path_omits_orientation_and_consensus_sections(self):
        report_input = _base_report_input(
            format_check={"forward": FileFormatCheck(filename="fwd.ab1", valid=True)},
            sanity_check={
                "forward": SanityCheckResult(n_proportion=0.0, raw_length=795, status="PASS")
            },
            trim={
                "forward": TrimResult(
                    trimmed_sequence="A" * 667,
                    trimmed_length=667,
                    trim_start=29,
                    trim_end=696,
                    trim_params={"quality_threshold": 20, "min_window_size": 50},
                )
            },
            ab1_extraction={
                "forward": ReadExtraction(
                    raw_sequence="A" * 795,
                    raw_length=795,
                    quality_scores=_quality_scores(795, seed=1),
                )
            },
            single_read_reason="single_file_provided",
            orientation=None,
            consensus=None,
            usability_check=UsabilityCheckResult(
                final_length=667, mean_quality=45.0, ambiguous_positions=0, status="PASS"
            ),
        )

        text = _extract_text(generate_report(report_input))

        assert "single_file_provided" in text
        assert "Consensus Building" not in text
        assert "Orientation Detection" not in text

    def test_ambiguous_positions_from_consensus_are_reported(self):
        report_input = _base_report_input(
            consensus=ConsensusResult(
                consensus_sequence="A" * 680,
                consensus_length=680,
                ambiguous_positions=[12, 340],
                quality_scores=[40] * 680,
            )
        )

        text = _extract_text(generate_report(report_input))

        assert "2 ambiguous position" in text
        assert "12" in text
        assert "340" in text

    def test_default_limitation_text_is_included(self):
        text = _extract_text(generate_report(_base_report_input()))

        assert DEFAULT_LIMITATION in text

    def test_custom_limitations_are_included_verbatim(self):
        report_input = _base_report_input(limitations=["Custom caveat about this specific run."])

        text = _extract_text(generate_report(report_input))

        assert "Custom caveat about this specific run." in text

    def test_thresholds_used_for_other_stages_are_rendered(self):
        report_input = _base_report_input(
            thresholds_used={"sanity_check": {"max_n_proportion": 0.5, "min_raw_length": 50}}
        )

        text = _extract_text(generate_report(report_input))

        assert "max_n_proportion" in text

    def test_reference_database_version_is_reported(self):
        text = _extract_text(generate_report(_base_report_input()))

        assert "v3" in text

    def test_raw_read_quality_section_reports_raw_length_and_phred_stats(self):
        scores_fwd = _quality_scores(795, seed=1)
        scores_rev = _quality_scores(1165, seed=2)

        text = _extract_text(generate_report(_base_report_input()))

        assert "Raw Read Quality" in text
        assert "raw length 795 bp" in text
        assert f"min {min(scores_fwd)}" in text
        assert f"mean {sum(scores_fwd) / len(scores_fwd):.1f}" in text
        assert f"max {max(scores_fwd)}" in text
        assert "raw length 1165 bp" in text
        assert f"min {min(scores_rev)}" in text
        assert f"mean {sum(scores_rev) / len(scores_rev):.1f}" in text
        assert f"max {max(scores_rev)}" in text

    def test_omits_raw_read_quality_section_when_extraction_data_absent(self):
        report_input = _base_report_input(ab1_extraction={})

        pdf_bytes = generate_report(report_input)
        text = _extract_text(pdf_bytes)

        assert pdf_bytes.startswith(b"%PDF")
        assert "Raw Read Quality" not in text


class TestWriteReportFile:
    def test_writes_the_exact_pdf_bytes(self, tmp_path):
        pdf_bytes = generate_report(_base_report_input())
        dest = tmp_path / "report.pdf"

        written_path = write_report_file(pdf_bytes, dest)

        assert written_path == dest
        assert dest.read_bytes() == pdf_bytes

    def test_creates_missing_parent_directories(self, tmp_path):
        pdf_bytes = generate_report(_base_report_input())
        dest = tmp_path / "runs" / "some-run-id" / "report.pdf"

        write_report_file(pdf_bytes, dest)

        assert dest.is_file()

    def test_written_file_is_a_valid_pdf(self, tmp_path):
        pdf_bytes = generate_report(_base_report_input())
        dest = tmp_path / "report.pdf"
        write_report_file(pdf_bytes, dest)

        reader = PdfReader(str(dest))

        assert len(reader.pages) >= 1
