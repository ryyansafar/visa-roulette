import pytest
from visa_roulette.flight import fly
from visa_roulette.imu_sim import synth_throw
from visa_roulette.throw import (
    GLOBE_KM_PER_M,
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


def test_range_comes_from_the_paper_plane_model_and_scales_to_the_globe():
    r = analyze_throw(samples(speed=8.0, elevation_deg=45.0, heading_deg=0.0))
    flown = fly(r.speed_mps, r.elevation_deg)
    assert r.range_m == pytest.approx(flown.range_m, rel=1e-6)
    assert r.distance_km == pytest.approx(r.range_m * GLOBE_KM_PER_M, rel=0.01)
    assert r.flight_s == pytest.approx(flown.flight_s) and r.path[0][3] > 0


def test_a_board_held_banked_right_curves_right():
    flat = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0))
    banked = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0, roll_deg=10.0))
    assert banked.bank_deg == pytest.approx(10.0, abs=0.5)
    assert banked.lateral_m > 1.0 and 5.0 < banked.heading_deg < 90.0
    assert banked.launch_heading_deg < 10.0 and banked.heading_deg > banked.launch_heading_deg + 8
    assert flat.bank_deg == pytest.approx(0.0, abs=0.1) and abs(flat.lateral_m) < 0.01


def test_a_board_banked_left_curves_left():
    left = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0, roll_deg=-10.0))
    assert left.lateral_m < -1.0 and 270.0 < left.heading_deg < 355.0


def test_a_tumbling_board_flies_worse_than_a_clean_one():
    clean = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0))
    tumble = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0, tumble=6.0))
    assert clean.flutter == pytest.approx(0.0, abs=0.1) and tumble.flutter > 3.0
    assert tumble.range_m < clean.range_m * 0.9


def test_a_barely_tilted_board_does_not_bank():
    r = analyze_throw(samples(speed=8.0, elevation_deg=30.0, heading_deg=0.0, roll_deg=1.0))
    assert r.bank_deg == 0.0


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


def test_a_throw_carries_the_attitude_samples_for_the_animation():
    result = analyze_throw(samples(speed=6.0, elevation_deg=25.0, heading_deg=0.0))
    assert len(result.pose) == len(result.path) > 10
    assert result.pose[0][0] == pytest.approx(25.0, abs=1.0)


def test_mpu6050_rows_with_gyro_channels_are_accepted():
    rows = synth_throw(speed=8.0, elevation_deg=30.0, heading_deg=0.0, gyro=True)
    assert all(len(row) == 7 for row in rows)
    result = analyze_throw([Sample(*row) for row in rows])
    assert result.speed_mps == pytest.approx(8.0, rel=0.1) and result.flutter == pytest.approx(0.0, abs=0.1)


def test_a_spinning_board_reads_as_flutter_from_the_gyro_alone():
    clean = analyze_throw([Sample(*row) for row in synth_throw(8.0, 30.0, 0.0, gyro=True)])
    spinning = analyze_throw([Sample(*row) for row in synth_throw(8.0, 30.0, 0.0, gyro=True, spin_rad_s=16.0)])
    assert spinning.flutter > 3.0 > clean.flutter
    assert spinning.range_m < clean.range_m * 0.9


def test_a_hard_throw_that_clips_the_accelerometer_still_registers():
    rows = [(t, *(max(-156.9, min(156.9, a)) for a in (ax, ay, az))) for t, ax, ay, az in synth_throw(14.0, 30.0, 0.0, push_s=0.05)]
    result = analyze_throw([Sample(*row) for row in rows])
    assert 5.0 < result.speed_mps <= 25.0
