import pytest

from visa_roulette.imu_sim import synth_throw
from visa_roulette.throw import (
    Sample,
    ThrowDetector,
    ThrowError,
    ThrowRejected,
    ThrowResult,
    analyze_throw,
    throw_from_flick,
    throw_from_power,
)


def samples(**kw):
    return [Sample(*row) for row in synth_throw(**kw)]


def test_forward_throw_speed_elevation_and_heading():
    r = analyze_throw(samples(speed=8.0, elevation_deg=45.0, heading_deg=0.0))
    assert r.speed_mps == pytest.approx(8.0, rel=0.1)
    assert r.elevation_deg == pytest.approx(45.0, abs=5)
    assert r.heading_deg == pytest.approx(0.0, abs=5) or r.heading_deg > 355
    assert r.source == "imu"


def test_throw_to_the_right_has_a_right_hand_heading():
    r = analyze_throw(samples(speed=7.0, elevation_deg=35.0, heading_deg=90.0))
    assert r.heading_deg == pytest.approx(90.0, abs=6)


def test_range_follows_ballistics_and_scales_to_the_globe():
    r = analyze_throw(samples(speed=8.0, elevation_deg=45.0, heading_deg=0.0))
    assert r.range_m == pytest.approx(8.0**2 / 9.81, rel=0.2)
    assert r.distance_km == pytest.approx(r.range_m * 1500, rel=0.01)


def test_distance_is_capped_to_half_the_planet():
    r = analyze_throw(samples(speed=20.0, elevation_deg=45.0, heading_deg=0.0))
    assert r.distance_km <= 19_000


def test_a_harder_throw_goes_further():
    soft = analyze_throw(samples(speed=5.0, elevation_deg=45.0, heading_deg=0.0))
    hard = analyze_throw(samples(speed=10.0, elevation_deg=45.0, heading_deg=0.0))
    assert hard.distance_km > soft.distance_km


def test_resting_board_is_not_a_throw():
    with pytest.raises(ThrowError):
        analyze_throw(samples(speed=0.0, elevation_deg=45.0, heading_deg=0.0, push_s=0.0))


def test_shaking_without_freefall_is_not_a_throw():
    shake = [Sample(i * 0.005, 0.0, 0.0, 9.81 + (40.0 if i % 20 < 4 else 0.0)) for i in range(400)]
    with pytest.raises(ThrowError):
        analyze_throw(shake)


def test_feeble_toss_is_rejected():
    with pytest.raises(ThrowError) as err:
        analyze_throw(samples(speed=1.0, elevation_deg=45.0, heading_deg=0.0, push_s=0.04))
    assert err.value.code == "too_weak"


def test_streaming_detector_reports_once_when_the_plane_lands():
    det = ThrowDetector()
    outcomes = [det.feed(s) for s in samples(speed=8.0, elevation_deg=45.0, heading_deg=0.0)]
    results = [o for o in outcomes if o is not None]
    assert len(results) == 1 and isinstance(results[0], ThrowResult)


def test_streaming_detector_reports_a_rejection():
    det = ThrowDetector()
    outcomes = [det.feed(s) for s in samples(speed=1.0, elevation_deg=45.0, heading_deg=0.0, push_s=0.04)]
    rejected = [o for o in outcomes if isinstance(o, ThrowRejected)]
    assert len(rejected) == 1 and rejected[0].code == "too_weak"


def test_streaming_detector_can_throw_twice():
    det = ThrowDetector()
    seen = [o for s in samples(speed=8.0, elevation_deg=45.0, heading_deg=0.0) if (o := det.feed(s))]
    seen += [o for s in samples(speed=6.0, elevation_deg=40.0, heading_deg=180.0) if (o := det.feed(s))]
    assert len(seen) == 2


def test_flick_up_the_screen_points_north():
    r = throw_from_flick(dx=0, dy=-300, dt_ms=100)
    assert r.heading_deg == pytest.approx(0.0, abs=0.01) and r.source == "flick"


def test_flick_right_points_east_and_faster_goes_further():
    slow = throw_from_flick(dx=100, dy=0, dt_ms=400)
    fast = throw_from_flick(dx=400, dy=0, dt_ms=100)
    assert slow.heading_deg == pytest.approx(90.0, abs=0.01)
    assert fast.distance_km > slow.distance_km


@pytest.mark.parametrize("args", [(0, 0, 100), (5, 5, 100), (100, 0, 0)])
def test_flick_that_is_not_a_flick_is_rejected(args):
    with pytest.raises(ThrowError):
        throw_from_flick(*args)


def test_switch_throw_uses_heading_and_power():
    weak = throw_from_power(heading_deg=225.0, power=0.1)
    strong = throw_from_power(heading_deg=225.0, power=1.0)
    assert weak.heading_deg == strong.heading_deg == 225.0
    assert strong.distance_km > weak.distance_km and strong.source == "switch"


@pytest.mark.parametrize("heading,power", [(-1, 0.5), (360, 0.5), (10, -0.1), (10, 1.1)])
def test_switch_throw_validates_input(heading, power):
    with pytest.raises(ThrowError):
        throw_from_power(heading, power)
