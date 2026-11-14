"""Location selection, kinds and request batching."""

from urllib.parse import urlencode

from custom_components.fogos_pt.api import MAX_QUERY_LENGTH, batch_location_params
from custom_components.fogos_pt.config_flow import build_title, default_warning_areas
from custom_components.fogos_pt.selection import Selection, incident_kind

from .conftest import AREAS


def test_query_sends_the_most_specific_level_of_each_branch():
    selection = Selection.from_options(
        {
            "districts": ["Porto", "Braga", "Ilha Da Madeira"],
            "concelhos": ["Braga|Guimarães", "Ilha Da Madeira|Funchal"],
            "freguesias": ["Ilha Da Madeira|Funchal|Sé"],
        }
    )

    assert selection.query() == {"district": ["Porto"], "concelho": ["Guimarães"], "freguesia": ["Sé"]}


def test_matches_is_exact_and_case_insensitive():
    selection = Selection.from_options({"districts": ["Porto", "Braga"], "concelhos": ["Braga|Guimarães"]})

    assert selection.matches({"district": "PORTO", "concelho": "Amarante"})
    assert selection.matches({"district": "Braga", "concelho": "guimarães"})
    assert not selection.matches({"district": "Braga", "concelho": "Barcelos"})
    # Same municipality name in another district.
    assert not selection.matches({"district": "Ilha De São Jorge", "concelho": "Guimarães"})
    assert Selection().matches({"district": "Faro"})


def test_kind_falls_back_to_natureza_code():
    assert incident_kind({"kind": "fma"}) == "fma"
    assert incident_kind({"naturezaCode": "3103"}) == "fire"
    assert incident_kind({"naturezaCode": "2101"}) == "urban_fire"
    assert incident_kind({"kind": "transportFire"}) == "transport_fire"
    assert incident_kind({"naturezaCode": "3315"}) == "fma"
    assert incident_kind({"naturezaCode": "9999"}) == "other"


def test_long_location_lists_are_split_into_short_requests():
    names = [f"União das freguesias de Lugar Número {i}, Outro e Mais" for i in range(80)]

    batches = batch_location_params({"freguesia": names}, {"all": "1"})

    assert len(batches) > 1
    assert all(len(urlencode(b)) <= MAX_QUERY_LENGTH for b in batches)
    assert [n for b in batches for n in b["freguesia"].split("|")] == names
    assert all(b["all"] == "1" for b in batches)
    assert batch_location_params({}, {"all": "1"}) == [{"all": "1"}]


def test_default_warning_areas_follow_the_locations():
    madeira = Selection.from_options({"districts": ["Ilha Da Madeira"]})
    funchal = Selection.from_options({"districts": ["Ilha Da Madeira"], "concelhos": ["Ilha Da Madeira|Funchal"]})

    assert default_warning_areas(AREAS, Selection.from_options({"districts": ["Porto"]})) == ["PTO"]
    assert default_warning_areas(AREAS, madeira) == ["MCN", "MCS", "MRM"]
    assert default_warning_areas(AREAS, funchal) == ["MCS", "MRM"]


def test_title():
    assert build_title(Selection()) == "Fogos.pt"
    assert build_title(Selection.from_options({"districts": ["Porto", "Braga"]})) == "Fogos.pt — Porto, Braga"
