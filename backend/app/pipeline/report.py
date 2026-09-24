"""Stage 11 -- Reporting.

Per CLAUDE.md: "every prior stage's data is assembled into one auditable
report ... final status, and stated limitations (e.g. 'expert-assistance
result, not a standalone forensic conclusion')." This module computes
nothing new -- it lays out ReportInput's already-typed fields (each one
some earlier stage's own finalized output) into a PDF via ReportLab, the
tool already pinned in requirements.txt.

Two functions, mirroring Stage 8's write_fasta_file() split between
in-memory content and disk materialization:

- generate_report(report_input) -> bytes: pure, returns raw PDF bytes.
  Kept storage-agnostic and directly testable, same reasoning as every
  other pipeline module -- no knowledge of Run ids or where a report
  "should" live.
- write_report_file(pdf_bytes, dest_path) -> Path: materializes those
  bytes to disk, creating parent directories as needed. The caller (a
  future orchestration layer) decides the destination, e.g.
  app.storage.run_dir(run_id) / "report.pdf".

One thing this module enforces regardless of what the caller passes:
IdentificationResult.taxonomic_consistency_checked is always False today
(see app/pipeline/identification.py's docstring -- no domain-provided
rule exists yet for CLAUDE.md's "taxonomically inconsistent" REVIEW
REQUIRED trigger). Rather than let a report silently omit that caveat,
generate_report() always appends a note about it to the Stated
Limitations section, on top of whatever ReportInput.limitations already
contains -- this is the exact place CLAUDE.md's Stage 10 status doc
predicted that flag would need to surface.
"""
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import DEFAULT_LIMITATION, ReportInput

TAXONOMIC_CONSISTENCY_NOTE = (
    "Taxonomic consistency was not checked for this identification -- "
    "no domain-reviewed rule exists for it yet."
)


def generate_report(report_input: ReportInput) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"PAIGS WildID Report -- {report_input.sample_id}",
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("PAIGS WildID -- Species Identification Report", styles["Title"]))
    story.append(Paragraph(f"Run ID: {report_input.run_id}", styles["Normal"]))
    story.append(Paragraph(f"Sample ID: {report_input.sample_id}", styles["Normal"]))
    story.append(
        Paragraph(f"Generated: {report_input.generated_at.isoformat()}", styles["Normal"])
    )
    story.append(
        Paragraph(
            f"Original file(s): {', '.join(report_input.original_filenames)}", styles["Normal"]
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Format Validity &amp; Sanity Check", styles["Heading2"]))
    for slot, format_check in report_input.format_check.items():
        format_line = (
            f"{slot.capitalize()} read -- format: "
            + ("valid" if format_check.valid else f"INVALID ({format_check.reason})")
        )
        story.append(Paragraph(format_line, styles["Normal"]))
        sanity = report_input.sanity_check.get(slot)
        if sanity is not None:
            sanity_line = (
                f"{slot.capitalize()} read -- sanity: {sanity.status} "
                f"(N proportion {sanity.n_proportion:.3f}, raw length {sanity.raw_length})"
            )
            if sanity.reason:
                sanity_line += f" -- {sanity.reason}"
            story.append(Paragraph(sanity_line, styles["Normal"]))
    if report_input.single_read_reason:
        story.append(
            Paragraph(f"Single-read path: {report_input.single_read_reason}", styles["Normal"])
        )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Trimming", styles["Heading2"]))
    for slot, trim in report_input.trim.items():
        trim_line = (
            f"{slot.capitalize()} read -- {trim.trimmed_length} bp kept "
            f"(window [{trim.trim_start}, {trim.trim_end})), params: {trim.trim_params}"
        )
        story.append(Paragraph(trim_line, styles["Normal"]))
    story.append(Spacer(1, 12))

    if report_input.orientation is not None:
        orientation = report_input.orientation
        story.append(Paragraph("Orientation Detection", styles["Heading2"]))
        orientation_line = f"Orientation: {orientation.orientation}"
        if orientation.overlap_length is not None and orientation.identity is not None:
            orientation_line += (
                f"; overlap {orientation.overlap_length} bp at "
                f"{orientation.identity * 100:.1f}% identity"
            )
        story.append(Paragraph(orientation_line, styles["Normal"]))
        if orientation.label_orientation_mismatch:
            story.append(
                Paragraph(
                    "NOTE: label/detected orientation mismatch -- the file uploaded to the "
                    "'reverse' slot was detected in a different orientation than its label "
                    "implied. Informational only, not blocking.",
                    styles["Normal"],
                )
            )
        story.append(Spacer(1, 12))

    if report_input.consensus is not None:
        consensus = report_input.consensus
        story.append(Paragraph("Consensus Building", styles["Heading2"]))
        consensus_line = f"Consensus length: {consensus.consensus_length} bp; "
        consensus_line += f"{len(consensus.ambiguous_positions)} ambiguous position(s)"
        if consensus.ambiguous_positions:
            consensus_line += f" at {consensus.ambiguous_positions}"
        story.append(Paragraph(consensus_line, styles["Normal"]))
        story.append(Spacer(1, 12))

    usability = report_input.usability_check
    story.append(Paragraph("Usability Check", styles["Heading2"]))
    usability_line = (
        f"Status: {usability.status} -- final length {usability.final_length} bp, "
        f"mean quality {usability.mean_quality:.1f}, "
        f"{usability.ambiguous_positions} ambiguous position(s)"
    )
    if usability.reason:
        usability_line += f" -- {usability.reason}"
    story.append(Paragraph(usability_line, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("FASTA", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Sequence ID: {report_input.fasta.sequence_id}; "
            f"length {report_input.fasta.sequence_length} bp",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 12))

    blast = report_input.blast
    story.append(Paragraph("BLAST Comparison", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Reference database version: {blast.database_version}; "
            f"query length {blast.query_length} bp; {len(blast.hits)} hit(s)",
            styles["Normal"],
        )
    )
    if blast.hits:
        table_data = [["Rank", "Species", "Identity %", "Coverage %", "E-value", "Bit score", "Accession"]]
        for hit in blast.hits:
            table_data.append(
                [
                    str(hit.rank),
                    hit.species,
                    f"{hit.identity:.2f}",
                    f"{hit.coverage:.2f}",
                    f"{hit.evalue:.2e}",
                    f"{hit.bit_score:.1f}",
                    hit.accession,
                ]
            )
        table = Table(table_data, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No hits returned.", styles["Normal"]))
    story.append(Spacer(1, 12))

    identification = report_input.identification
    story.append(Paragraph("Identification", styles["Heading2"]))
    status_line = f"Final status: {identification.status}"
    if identification.reason:
        status_line += f" -- {identification.reason}"
    story.append(Paragraph(status_line, styles["Heading3"]))
    if identification.candidate_species:
        story.append(
            Paragraph(
                f"Candidate species: {identification.candidate_species} "
                f"(identity {identification.identity:.2f}%, coverage {identification.coverage:.2f}%)",
                styles["Normal"],
            )
        )
    story.append(
        Paragraph(f"Thresholds applied: {identification.thresholds_applied}", styles["Normal"])
    )
    story.append(Spacer(1, 12))

    if report_input.thresholds_used:
        story.append(Paragraph("Other Thresholds Applied", styles["Heading2"]))
        for stage_name, thresholds in report_input.thresholds_used.items():
            story.append(Paragraph(f"{stage_name}: {thresholds}", styles["Normal"]))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Stated Limitations", styles["Heading2"]))
    limitations = list(report_input.limitations)
    if not identification.taxonomic_consistency_checked:
        limitations.append(TAXONOMIC_CONSISTENCY_NOTE)
    for limitation in limitations:
        story.append(Paragraph(f"• {limitation}", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


def write_report_file(pdf_bytes: bytes, dest_path) -> Path:
    """Materialize generate_report()'s PDF bytes to a real file -- same
    storage-agnostic convention as app.pipeline.fasta.write_fasta_file():
    no knowledge of Run ids or storage layout, the caller decides the
    destination."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(pdf_bytes)
    return dest_path
