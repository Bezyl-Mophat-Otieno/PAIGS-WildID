"""app.reference.bold -- fetching candidate reference records from the
real BOLD Portal API (portal.boldsystems.org).

No real network call in any of these -- httpx.MockTransport stands in
for BOLD's three-endpoint flow (preprocessor -> query -> documents
download), using response shapes verified live against the real API
while building this module (see app.reference.bold's own module
docstring for why the older, widely-cited "API_Public" REST API no
longer applies).
"""
import json

import httpx
import pytest

from app.reference.bold import BoldApiError, fetch_bold_taxon

BASE = "https://portal.boldsystems.org/api"


def _record(
    process_id,
    species,
    *,
    identification_rank="species",
    identification=None,
    bin_uri="BOLD:AAA0001",
    nuc="ACGT" * 100,
    genus=None,
    family="Felidae",
):
    return {
        "processid": process_id,
        "identification_rank": identification_rank,
        "identification": identification if identification is not None else species,
        "bin_uri": bin_uri,
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Mammalia",
        "order": "Carnivora",
        "family": family,
        "genus": genus or (species.split(" ")[0] if species else None),
        "species": species,
        "nuc": nuc,
    }


def _mock_client(records, *, query_id="FAKE_TOKEN", recognized=True):
    ndjson = "\n".join(json.dumps(r) for r in records)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/query/preprocessor"):
            if not recognized:
                return httpx.Response(200, json={"successful_terms": []})
            return httpx.Response(
                200, json={"successful_terms": [{"submitted": "x", "matched": "x"}]}
            )
        if path.endswith("/query"):
            return httpx.Response(200, json={"query_id": query_id, "extent_limit": None})
        if f"/documents/{query_id}/download" in path:
            return httpx.Response(200, text=ndjson)
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)


class TestFetchBoldTaxon:
    def test_builds_fasta_and_summary_for_clean_records(self):
        records = [
            _record("AAA001-01", "Panthera leo", bin_uri="BOLD:AAA0001"),
            _record("AAA002-01", "Panthera leo", bin_uri="BOLD:AAA0001"),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.total_fetched == 2
        assert result.total_kept == 2
        assert ">AAA001-01 Panthera leo | Animalia;Chordata;Mammalia;Carnivora;Felidae;Panthera;Panthera leo" in result.fasta_content
        assert "ACGT" * 100 in result.fasta_content
        assert len(result.species) == 1
        assert result.species[0].species == "Panthera leo"
        assert result.species[0].kept_count == 2
        assert result.species[0].bin_consistent is True

    def test_drops_records_not_identified_to_species_level(self):
        records = [
            _record("AAA001-01", "Panthera leo"),
            _record("AAA002-01", None, identification_rank="genus"),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.total_fetched == 2
        assert result.total_kept == 1
        assert result.drop_reasons["not identified to species level"] == 1

    def test_subspecies_rank_is_kept_even_in_required_mode(self):
        """Discovered live against the real API: a subspecies-ranked BOLD
        record's own `species` field already holds a clean binomial (the
        extra epithet only lives in `identification`) -- a subspecies-
        confirmed identification is strictly *more* precise than
        species-level, not less, and must not need
        require_species_level="allow_lower_rank" to be admitted, nor get
        counted in total_kept_at_lower_rank."""
        records = [
            _record(
                "AAA001-01",
                "Manis pentadactyla",
                identification_rank="subspecies",
                identification="Manis pentadactyla pentadactyla",
            ),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Manis", http_client=client)

        assert result.total_kept == 1
        assert result.total_kept_at_lower_rank == 0
        assert result.species[0].species == "Manis pentadactyla"
        assert result.species[0].identification_rank == "subspecies"
        assert "Manis pentadactyla pentadactyla" not in result.fasta_content

    def test_allow_lower_rank_keeps_records_using_the_identification_field(self):
        """require_species_level="allow_lower_rank" is a deliberate risk
        trade (see DEFAULT_REQUIRE_SPECIES_LEVEL's own comment): a
        genus-only record is kept, grouped under BOLD's own overall
        `identification` field (since `species` itself is blank), and
        counted separately as total_kept_at_lower_rank so a reviewer
        can't miss it."""
        records = [
            _record("AAA001-01", "Panthera leo"),
            _record(
                "AAA002-01", None, identification_rank="genus", identification="Panthera"
            ),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon(
            "Panthera", require_species_level="allow_lower_rank", http_client=client
        )

        assert result.total_fetched == 2
        assert result.total_kept == 2
        assert result.total_kept_at_lower_rank == 1
        assert "not identified to species level" not in result.drop_reasons

        lower_rank_entry = next(s for s in result.species if s.species == "Panthera")
        assert lower_rank_entry.identification_rank == "genus"
        assert lower_rank_entry.kept_count == 1

        species_entry = next(s for s in result.species if s.species == "Panthera leo")
        assert species_entry.identification_rank == "species"

    def test_allow_lower_rank_still_drops_records_with_no_identification_at_all(self):
        records = [
            _record("AAA001-01", None, identification_rank="genus", identification=""),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon(
            "Panthera", require_species_level="allow_lower_rank", http_client=client
        )

        assert result.total_kept == 0
        assert result.drop_reasons["no identification available at any rank"] == 1

    def test_drops_too_short_sequences(self):
        records = [
            _record("AAA001-01", "Panthera leo", nuc="ACGT" * 100),
            _record("AAA002-01", "Panthera leo", nuc="ACGT"),  # 4bp, well under the floor
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.total_kept == 1
        assert result.drop_reasons["sequence too short or too ambiguous"] == 1

    def test_drops_sequences_with_too_many_ambiguous_bases(self):
        mostly_n = "N" * 400 + "ACGT" * 50
        records = [_record("AAA001-01", "Panthera leo", nuc=mostly_n)]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.total_kept == 0
        assert result.drop_reasons["sequence too short or too ambiguous"] == 1

    def test_enforces_max_records_per_species_cap(self):
        records = [
            _record(f"AAA00{i}-01", "Panthera leo", bin_uri="BOLD:AAA0001") for i in range(5)
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", max_records_per_species=2, http_client=client)

        assert result.total_kept == 2
        assert result.drop_reasons["over the per-species cap"] == 3
        assert result.species[0].kept_count == 2
        assert result.species[0].dropped_count == 3

    def test_flags_bin_inconsistency_within_one_species(self):
        records = [
            _record("AAA001-01", "Panthera leo", bin_uri="BOLD:AAA0001"),
            _record("AAA002-01", "Panthera leo", bin_uri="BOLD:AAA9999"),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.species[0].bin_consistent is False

    def test_flags_species_sharing_a_bin(self):
        records = [
            _record("AAA001-01", "Panthera leo", bin_uri="BOLD:SHARED"),
            _record("AAA002-01", "Panthera pardus", bin_uri="BOLD:SHARED"),
        ]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.species_sharing_a_bin == [["Panthera leo", "Panthera pardus"]]

    def test_zero_kept_records_after_filtering_is_not_an_error(self):
        records = [_record("AAA001-01", None, identification_rank="genus")]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert result.total_kept == 0
        assert result.species == []

    def test_raises_bold_api_error_for_unrecognized_taxon(self):
        client = _mock_client([], recognized=False)

        with pytest.raises(BoldApiError, match="didn't recognize"):
            fetch_bold_taxon("Notarealtaxonxyz", http_client=client)

    def test_raises_bold_api_error_on_query_http_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/query/preprocessor"):
                return httpx.Response(200, json={"successful_terms": [{"submitted": "x", "matched": "x"}]})
            if request.url.path.endswith("/query"):
                return httpx.Response(500, json={"detail": "server error"})
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)

        with pytest.raises(BoldApiError, match="query endpoint failed"):
            fetch_bold_taxon("Panthera", http_client=client)

    def test_taxonomy_string_omits_blank_ranks(self):
        records = [_record("AAA001-01", "Panthera leo", family=None)]
        client = _mock_client(records)

        result = fetch_bold_taxon("Panthera", http_client=client)

        assert "Felidae" not in result.fasta_content
        assert "Animalia;Chordata;Mammalia;Carnivora;Panthera;Panthera leo" in result.fasta_content
