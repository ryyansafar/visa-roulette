from visa_roulette.profile import VisaHeld
from visa_roulette.visa import needs, reachable, requirement


def held(country, kind="tourist"):
    return VisaHeld(country=country, kind=kind)


def test_home_country_needs_nothing():
    assert requirement("IND", "IND").status == "home"


def test_listed_visa_free_destination():
    verdict = requirement("IND", "BTN")
    assert verdict.status == "free" and verdict.as_of and verdict.verified is False


def test_unlisted_destination_is_unknown_not_a_guess():
    verdict = requirement("IND", "TKM")
    assert verdict.status == "unknown" and "official" in verdict.note.lower()


def test_unlisted_nationality_is_unknown():
    assert requirement("NRU", "BTN").status == "unknown"


def test_a_held_visa_for_the_destination_wins():
    assert requirement("IND", "AUS", [held("AUS")]).status == "held"


def test_another_visa_can_unlock_a_destination():
    plain = requirement("IND", "ARE")
    unlocked = requirement("IND", "ARE", [held("USA")])
    assert plain.status == "evisa"
    assert unlocked.status == "on_arrival" and unlocked.unlocked_by == "USA"


def test_schengen_visa_counts_for_any_member_state():
    assert requirement("IND", "ARE", [held("FRA")]).unlocked_by == "FRA"


def test_reachable_maps_every_listed_country():
    result = reachable("IND", [held("USA")])
    assert result["BTN"] == "free" and result["ARE"] == "on_arrival" and "TKM" not in result


def test_required_visa_lists_embassy_documents_without_duplicates():
    ids = [item["id"] for item in needs("required", "CHN")["items"]]
    assert "appointment" in ids and "form" in ids and len(ids) == len(set(ids))


def test_dubai_adds_its_own_documents_and_official_link():
    result = needs("evisa", "ARE")
    assert "uae_hotel" in [item["id"] for item in result["items"]]
    assert result["official_url"].startswith("https://")


def test_home_and_unknown_ask_for_nothing_invented():
    assert [item["id"] for item in needs("home", "IND")["items"]] == ["passport_id"]
    assert needs("unknown", "ISL")["items"] == []


def test_schengen_needs_a_visa_for_an_indian_passport_and_unlocks_nothing_by_itself():
    assert requirement("IND", "FRA").status == "required"


def test_every_nationality_has_rules_and_no_destination_has_two_statuses():
    from visa_roulette.visa import _rules

    rules = _rules()["nationalities"]
    assert {"IND", "USA", "GBR", "ARE"} <= set(rules)
    for entry in rules.values():
        codes = [code for status in ("free", "on_arrival", "evisa", "required") for code in entry.get(status, [])]
        assert len(codes) == len(set(codes))
