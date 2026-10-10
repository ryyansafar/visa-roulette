import math

import pytest

from visa_roulette.flight import RELEASE_HEIGHT_M, fly


def test_the_path_starts_at_the_hand_and_ends_on_the_ground():
    flight = fly(speed=7.0, elevation_deg=30.0)
    first, last = flight.path[0], flight.path[-1]
    assert first[0] == 0.0 and first[3] == pytest.approx(RELEASE_HEIGHT_M)
    assert last[3] == pytest.approx(0.0, abs=0.05)
    assert last[0] == pytest.approx(flight.flight_s, abs=0.05)
    assert all(b[0] > a[0] for a, b in zip(flight.path, flight.path[1:]))


def test_a_harder_throw_goes_further():
    assert fly(10.0, 30.0).range_m > fly(5.0, 30.0).range_m


def test_a_steep_launch_climbs_higher_but_gives_up_its_forward_speed():
    steep, flat = fly(8.0, 85.0), fly(8.0, 5.0)
    assert max(p[3] for p in steep.path) > max(p[3] for p in flat.path) + 0.3
    apex = max(steep.path, key=lambda p: p[3])
    assert apex[1] < 1.0


def test_a_nose_down_launch_is_shortest():
    assert fly(8.0, -30.0).range_m < fly(8.0, 30.0).range_m


def test_a_gentle_toss_glides_instead_of_dropping():
    flight = fly(speed=3.0, elevation_deg=0.0)
    drop_time = math.sqrt(2 * RELEASE_HEIGHT_M / 9.81)
    assert flight.flight_s > drop_time * 1.3
    assert flight.range_m > RELEASE_HEIGHT_M * 3


def test_banking_right_curves_the_flight_right():
    straight, right, left = fly(7.0, 25.0), fly(7.0, 25.0, bank_deg=10.0), fly(7.0, 25.0, bank_deg=-10.0)
    assert straight.lateral_m == pytest.approx(0.0, abs=1e-6)
    assert right.lateral_m > 0.5 and left.lateral_m < -0.5
    assert right.lateral_m == pytest.approx(-left.lateral_m, rel=1e-6)


def test_a_wobbling_launch_loses_range():
    assert fly(8.0, 30.0, flutter=6.0).range_m < fly(8.0, 30.0).range_m * 0.85


def test_the_same_throw_gives_the_same_flight():
    assert fly(7.0, 30.0, bank_deg=10.0) == fly(7.0, 30.0, bank_deg=10.0)


@pytest.mark.parametrize("speed", [2.5, 12.0, 25.0])
def test_extreme_speeds_stay_physical(speed):
    flight = fly(speed, 45.0)
    assert 0.5 < flight.range_m < 60.0 and 0.3 < flight.flight_s <= 8.0
    assert max(point[3] for point in flight.path) < 40.0


def test_the_path_is_light_enough_to_send_to_the_browser():
    assert len(fly(12.0, 30.0).path) <= 120
