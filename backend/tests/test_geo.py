import pytest
from visa_roulette import geo


def test_destination_east_along_the_equator():
    lat, lon = geo.destination(0.0, 0.0, 90.0, 111.195)
    assert lat == pytest.approx(0.0, abs=0.01)
    assert lon == pytest.approx(1.0, abs=0.01)


def test_destination_north_and_longitude_wraps():
    lat, _ = geo.destination(0.0, 0.0, 0.0, 1000.0)
    assert lat == pytest.approx(8.99, abs=0.02)
    _, lon = geo.destination(0.0, 179.5, 90.0, 111.195)
    assert -180 <= lon < 180
    assert lon == pytest.approx(-179.5, abs=0.02)


def test_country_at_known_points():
    assert geo.country_at(48.85, 2.35).iso3 == "FRA"
    assert geo.country_at(28.6, 77.2).iso3 == "IND"
    assert geo.country_at(25.2, 55.3).iso3 == "ARE"


def test_open_ocean_has_no_country():
    assert geo.country_at(0.0, -30.0) is None


def test_land_on_land_is_not_snapped():
    landing = geo.land(28.6, 77.2)
    assert (landing.iso3, landing.snapped) == ("IND", False)


def test_land_on_ocean_snaps_to_nearest_country():
    landing = geo.land(0.0, -30.0)
    assert landing.snapped is True
    assert landing.iso3 and landing.name
    assert landing.snap_km > 0


def test_country_registry_and_centroid():
    assert geo.is_country("IND") and geo.is_country("ARE")
    assert not geo.is_country("XXX")
    lat, lon = geo.country_centroid("IND")
    assert 8 < lat < 35 and 68 < lon < 97


def test_unknown_country_centroid_is_a_value_error():
    with pytest.raises(ValueError):
        geo.country_centroid("XXX")


def test_resolve_landing_from_a_country_throw():
    landing = geo.resolve_landing("IND", heading_deg=270.0, distance_km=2000.0)
    assert landing.iso3 and landing.iso3 != "IND"
    assert abs(landing.distance_km - 2000.0) <= landing.snap_km + 5  # only the snap may move it


def test_country_list_is_sorted_unique_and_complete_enough():
    countries = geo.countries()
    names = [c.name for c in countries]
    assert names == sorted(names)
    assert len({c.iso3 for c in countries}) == len(countries) > 150
    assert geo.Country("IND", "India") in countries


def test_landing_restricted_to_allowed_countries_snaps_into_them():
    allowed = frozenset({"IND", "NPL", "BTN"})
    landing = geo.land(-14.2, -51.9, allowed)  # Brazil: not in the allowed set
    assert landing.iso3 in allowed and landing.snapped is True


def test_landing_inside_an_allowed_country_is_not_snapped():
    landing = geo.land(28.6, 77.2, frozenset({"IND"}))
    assert (landing.iso3, landing.snapped) == ("IND", False)


def test_landing_with_nothing_allowed_is_an_error():
    with pytest.raises(ValueError):
        geo.land(0.0, 0.0, frozenset({"ZZZ"}))
