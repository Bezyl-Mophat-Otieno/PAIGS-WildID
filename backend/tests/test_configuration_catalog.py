"""Configuration subsystem -- catalog tests.

The catalog (app.configuration.catalog.CATALOG) is the single source of
truth for what's configurable. These tests guard its two most important
invariants: every default value is pulled live from its own pipeline
module's DEFAULT_* constant (never retyped, so it can't silently drift),
and every catalog key is unique and well-formed.
"""
from app.configuration.catalog import CATALOG, CATALOG_BY_KEY
from app.pipeline.blast import DEFAULT_MAX_HITS
from app.pipeline.identification import (
    DEFAULT_AMBIGUOUS_MARGIN_PCT,
    DEFAULT_MIN_COVERAGE_PCT,
    DEFAULT_MIN_IDENTITY_PCT,
)
from app.pipeline.orientation import DEFAULT_MIN_IDENTITY, DEFAULT_MIN_OVERLAP_LENGTH
from app.pipeline.sanity_check import DEFAULT_MAX_N_PROPORTION, DEFAULT_MIN_RAW_LENGTH
from app.pipeline.trim import DEFAULT_MIN_WINDOW_SIZE, DEFAULT_QUALITY_THRESHOLD
from app.pipeline.usability_check import (
    DEFAULT_MAX_AMBIGUOUS_PROPORTION,
    DEFAULT_MIN_LENGTH,
    DEFAULT_MIN_MEAN_QUALITY,
)

EXPECTED_DEFAULTS = {
    "sanity_check.max_n_proportion": DEFAULT_MAX_N_PROPORTION,
    "sanity_check.min_raw_length": DEFAULT_MIN_RAW_LENGTH,
    "trim.quality_threshold": DEFAULT_QUALITY_THRESHOLD,
    "trim.min_window_size": DEFAULT_MIN_WINDOW_SIZE,
    "orientation.min_overlap_length": DEFAULT_MIN_OVERLAP_LENGTH,
    "orientation.min_identity": DEFAULT_MIN_IDENTITY,
    "usability_check.min_length": DEFAULT_MIN_LENGTH,
    "usability_check.min_mean_quality": DEFAULT_MIN_MEAN_QUALITY,
    "usability_check.max_ambiguous_proportion": DEFAULT_MAX_AMBIGUOUS_PROPORTION,
    "blast.max_hits": DEFAULT_MAX_HITS,
    "identification.min_identity_pct": DEFAULT_MIN_IDENTITY_PCT,
    "identification.min_coverage_pct": DEFAULT_MIN_COVERAGE_PCT,
    "identification.ambiguous_margin_pct": DEFAULT_AMBIGUOUS_MARGIN_PCT,
}

# The three non-numeric ("enum"/"string") keys added for the
# remote-vs-local BLAST search decision -- not part of EXPECTED_DEFAULTS
# above since they don't map to a pipeline module's own DEFAULT_*
# constant, and aren't cast through float().
NON_NUMERIC_DEFAULTS = {
    "blast.mode": "remote",
    "blast.remote_database": "nt",
    "blast.entrez_query": "",
}


def test_catalog_has_exactly_the_expected_keys():
    assert {d.key for d in CATALOG} == set(EXPECTED_DEFAULTS) | set(NON_NUMERIC_DEFAULTS)


def test_catalog_keys_are_unique():
    keys = [d.key for d in CATALOG]
    assert len(keys) == len(set(keys))


def test_every_default_matches_its_pipeline_modules_own_constant():
    for key, expected in EXPECTED_DEFAULTS.items():
        assert CATALOG_BY_KEY[key].default == float(expected), key


def test_key_is_stage_type_dot_param_name():
    for definition in CATALOG:
        assert definition.key == f"{definition.stage_type}.{definition.param_name}"


def test_value_type_matches_the_default_constants_own_python_type():
    int_keys = {
        "sanity_check.min_raw_length",
        "trim.quality_threshold",
        "trim.min_window_size",
        "orientation.min_overlap_length",
        "usability_check.min_length",
        "blast.max_hits",
    }
    enum_keys = {"blast.mode", "blast.remote_database"}
    string_keys = {"blast.entrez_query"}
    for definition in CATALOG:
        if definition.key in enum_keys:
            expected = "enum"
        elif definition.key in string_keys:
            expected = "string"
        elif definition.key in int_keys:
            expected = "int"
        else:
            expected = "float"
        assert definition.value_type == expected, definition.key


class TestNonNumericEntries:
    """blast.mode / blast.remote_database / blast.entrez_query -- the
    three keys added for the remote-vs-local BLAST search decision (see
    claude/remote-blast-search.md). Unlike every other catalog entry,
    these aren't "int"/"float" thresholds validated against `bounds`;
    they're a fixed choice ("enum", validated against `choices`) or free
    text ("string")."""

    def test_defaults_match_the_documented_remote_first_design(self):
        for key, expected in NON_NUMERIC_DEFAULTS.items():
            assert CATALOG_BY_KEY[key].default == expected, key

    def test_blast_mode_is_an_enum_defaulting_to_remote_with_local_selectable(self):
        definition = CATALOG_BY_KEY["blast.mode"]
        assert definition.value_type == "enum"
        assert definition.default == "remote"
        assert definition.choices == ("remote", "local")

    def test_blast_remote_database_is_an_enum_with_nt_as_the_default(self):
        definition = CATALOG_BY_KEY["blast.remote_database"]
        assert definition.value_type == "enum"
        assert definition.default == "nt"
        assert set(definition.choices) >= {"nt", "refseq_rna", "refseq_genomic"}

    def test_blast_entrez_query_is_free_text_with_no_choices(self):
        definition = CATALOG_BY_KEY["blast.entrez_query"]
        assert definition.value_type == "string"
        assert definition.default == ""
        assert definition.choices is None

    def test_non_numeric_entries_have_no_numeric_bounds(self):
        for key in NON_NUMERIC_DEFAULTS:
            assert CATALOG_BY_KEY[key].bounds == (None, None)


def test_proportion_and_probability_keys_have_zero_one_bounds():
    proportion_keys = {
        "sanity_check.max_n_proportion",
        "orientation.min_identity",
        "usability_check.max_ambiguous_proportion",
    }
    for key in proportion_keys:
        assert CATALOG_BY_KEY[key].bounds == (0.0, 1.0)


def test_percentage_keys_have_zero_hundred_bounds():
    percentage_keys = {
        "identification.min_identity_pct",
        "identification.min_coverage_pct",
        "identification.ambiguous_margin_pct",
    }
    for key in percentage_keys:
        low, high = CATALOG_BY_KEY[key].bounds
        assert low == 0.0
        assert high == 100.0
