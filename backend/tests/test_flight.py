import math

import pytest
from visa_roulette.flight import (
    RELEASE_HEIGHT_M,
    drag_coefficient,
    fly,
    lift_coefficient,
    trim_speed,
)


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
    assert max(p[3] for p in steep.path) > RELEASE_HEIGHT_M + 1.0
    apex = max(steep.path, key=lambda p: p[3])
    assert apex[1] < 1.0


def test_a_nose_down_launch_is_shortest():
    assert fly(8.0, -60.0).range_m < fly(8.0, 30.0).range_m


def test_a_gentle_toss_glides_instead_of_dropping():
    flight = fly(speed=3.0, elevation_deg=0.0)
    drop_time = math.sqrt(2 * RELEASE_HEIGHT_M / 9.81)
    assert flight.flight_s > drop_time * 1.3
    assert flight.range_m > RELEASE_HEIGHT_M * 2


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
    flight = fly(12.0, 30.0)
    assert len(flight.path) <= 340 and len(flight.path) == len(flight.pose)


def test_cruise_lift_matches_measured_paper_dart_data():
    # flight tests: CL 0.17-0.19 at about 5 degrees, lift-to-drag about 5
    cl = lift_coefficient(5.0)
    assert 0.16 <= cl <= 0.22
    assert 4.3 <= cl / drag_coefficient(5.0) <= 6.0


def test_lift_peaks_near_thirty_degrees_then_stalls():
    angles = [a / 2 for a in range(0, 161)]
    peak = max(angles, key=lift_coefficient)
    assert 25.0 <= peak <= 42.0
    assert 1.1 <= lift_coefficient(peak) <= 1.6
    assert lift_coefficient(70.0) < lift_coefficient(peak) * 0.8
    assert lift_coefficient(-5.0) == pytest.approx(-lift_coefficient(5.0))


def test_drag_grows_with_angle_of_attack():
    assert drag_coefficient(30.0) > drag_coefficient(10.0) > drag_coefficient(0.0) > 0.0


def test_trim_speed_matches_the_measured_flight_speed():
    assert 3.5 <= trim_speed() <= 6.0


def test_a_typical_hand_throw_flies_a_few_seconds_and_several_metres():
    flight = fly(speed=4.9, elevation_deg=10.0)
    assert 1.0 <= flight.flight_s <= 4.5
    assert 4.0 <= flight.range_m <= 20.0


def test_a_trimmed_glide_covers_about_five_times_the_height_it_loses():
    glide_deg = -math.degrees(math.atan(1 / 5))
    flight = fly(speed=trim_speed(), elevation_deg=glide_deg)
    assert 3.5 <= flight.range_m / RELEASE_HEIGHT_M <= 7.5


def test_the_plane_never_gains_energy_in_flight():
    flight = fly(speed=8.0, elevation_deg=20.0)
    pts = flight.path
    energies = []
    for a, b in zip(pts, pts[1:]):
        dt = b[0] - a[0]
        v = math.sqrt(((b[1] - a[1]) / dt) ** 2 + ((b[2] - a[2]) / dt) ** 2 + ((b[3] - a[3]) / dt) ** 2)
        energies.append(0.5 * v * v + 9.81 * a[3])
    assert max(energies[3:]) <= energies[0] * 1.05 + 0.5


def test_pose_starts_at_the_launch_attitude_and_levels_the_wings():
    flight = fly(speed=6.0, elevation_deg=25.0, bank_deg=12.0)
    pitch0, bank0 = flight.pose[0]
    assert pitch0 == pytest.approx(25.0, abs=1.0) and bank0 == pytest.approx(12.0, abs=0.5)
    assert abs(flight.pose[-1][1]) < abs(bank0)
    assert all(abs(p) <= 90.0 and abs(b) <= 45.0 for p, b in flight.pose)


def test_a_nose_up_launch_pitches_over_into_a_glide():
    flight = fly(speed=7.0, elevation_deg=40.0)
    assert flight.pose[0][0] > 30.0
    assert min(p for p, _ in flight.pose) < 5.0
