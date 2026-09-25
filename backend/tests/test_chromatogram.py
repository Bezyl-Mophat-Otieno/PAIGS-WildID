"""app.pipeline.chromatogram -- raw AB1 chromatogram/peak data.

Item 6 of the user's punch list: "Add an endpoint to expose the raw AB1
chromatogram/peak data. Every AB1 file already contains this, but
nothing serves it today. Needed so an analyst can visually double-check
a flagged or low-confidence base call instead of just trusting a
number." Already anticipated in docs/PLAN.md's own "Chromatogram
viewer" future-frontend note, which names the exact raw ABIF tags this
reads: DATA9-DATA12 (the four fluorescence channels) and PLOC2 (per-base
peak locations), both under record.annotations["abif_raw"].

Written first, against the not-yet-existing app.pipeline.chromatogram
module, to confirm red before implementing. Function-level only (like
Stage 1/2's own tests) -- HTTP-level tests for the GET
/runs/{id}/chromatogram/{slot} endpoint live in test_api_chromatogram.py.
"""
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestExtractChromatogram:
    def test_channel_order_comes_from_the_files_own_fwo_tag(self):
        from app.pipeline.chromatogram import extract_chromatogram

        result = extract_chromatogram(FIXTURES / "3100.ab1")

        # Confirmed directly against this fixture's real FWO_1 tag --
        # never hard-coded, since ABIF allows the channel order to vary
        # file to file.
        assert result.channel_order == ["G", "A", "T", "C"]

    def test_all_four_channels_are_present_and_the_same_length(self):
        from app.pipeline.chromatogram import extract_chromatogram

        result = extract_chromatogram(FIXTURES / "3100.ab1")

        assert set(result.trace.keys()) == {"G", "A", "T", "C"}
        lengths = {len(samples) for samples in result.trace.values()}
        assert lengths == {result.num_samples}
        assert result.num_samples > 0

    def test_peak_locations_line_up_one_per_base_call(self):
        from app.pipeline.chromatogram import extract_chromatogram

        result = extract_chromatogram(FIXTURES / "3100.ab1")

        assert len(result.peak_locations) == len(result.base_calls)
        assert len(result.base_calls) == 795  # same base-called length as test_ab1_extraction.py

    def test_peak_locations_are_valid_indexes_into_the_trace(self):
        from app.pipeline.chromatogram import extract_chromatogram

        result = extract_chromatogram(FIXTURES / "3100.ab1")

        assert all(0 <= loc < result.num_samples for loc in result.peak_locations)
        # Peak locations move forward through the trace as bases are
        # called in order (a real chromatogram never jumps backwards).
        assert result.peak_locations == sorted(result.peak_locations)

    def test_extracts_second_fixture_too(self):
        from app.pipeline.chromatogram import extract_chromatogram

        result = extract_chromatogram(FIXTURES / "3730.ab1")

        assert result.num_samples > 0
        assert len(result.peak_locations) == len(result.base_calls) > 0
