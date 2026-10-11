import pytest
from fastapi.testclient import TestClient
from visa_roulette.airmouse import ClickDetector, ClickTracker, MouseStepper
from visa_roulette.api import create_app
from visa_roulette.imu_sim import synth_throw
from visa_roulette.throw import G, Sample, ThrowDetector

HZ = 500


def hold(seconds, t0=0.0, mag=G, gy=0.0, gz=0.0):
    return [Sample(t0 + i / HZ, 0.0, 0.0, mag, 0.0, gy, gz) for i in range(round(seconds * HZ))]


def move(samples):
    stepper, dx, dy = MouseStepper(), 0.0, 0.0
    for sample in samples:
        delta = stepper.feed(sample)
        if delta:
            dx, dy = dx + delta.dx, dy + delta.dy
    return dx, dy


def tap(t0, spike_s=0.02, peak=4.0 * G):
    spike = [Sample(t0 + i / HZ, 0.0, 0.0, peak) for i in range(round(spike_s * HZ))]
    return spike + hold(0.1, t0 + spike_s)


def clicks_in(samples):
    detector = ClickDetector()
    return sum(detector.feed(s) for s in samples)


def test_rest_and_noise_inside_the_deadzone_do_not_move_the_cursor():
    assert move(hold(1.0, gz=0.04, gy=-0.03)) == (0.0, 0.0)


def test_yaw_moves_x_and_pitch_moves_y_with_the_gain():
    dx, dy = move(hold(0.5, gz=-1.0))
    assert dx == pytest.approx(0.94 * 900 * 0.5, rel=0.1) and dy == 0.0
    dx, dy = move(hold(0.5, gy=1.0))
    assert dy == pytest.approx(0.94 * 900 * 0.5, rel=0.1) and dx == 0.0


def test_deltas_are_throttled_to_about_30_hz():
    stepper = MouseStepper()
    events = [d for d in (stepper.feed(s) for s in hold(1.0, gz=1.0)) if d]
    assert 28 <= len(events) <= 31


def test_a_sharp_tap_is_one_click():
    assert clicks_in(hold(0.3) + tap(0.3) + hold(0.3, 0.42)) == 1


def test_two_quick_taps_a_tenth_of_a_second_apart_are_two_clicks():
    first = [Sample(0.3 + i / HZ, 0.0, 0.0, 4.0 * G) for i in range(10)]
    second = [Sample(0.42 + i / HZ, 0.0, 0.0, 4.0 * G) for i in range(10)]
    assert clicks_in(hold(0.3) + first + hold(0.1, 0.32) + second + hold(0.2, 0.44)) == 2


def test_a_long_push_is_not_a_click():
    assert clicks_in(hold(0.3) + tap(0.3, spike_s=0.2)) == 0


def test_a_throw_trace_is_never_a_click_and_still_a_throw():
    rows = synth_throw(8.0, 45.0, 0.0, hz=HZ, gyro=True)
    samples = [Sample(*row) for row in rows]
    assert clicks_in(samples[:-int(0.5 * HZ) - 1]) == 0
    detector, outcomes = ThrowDetector(), []
    for sample in samples:
        outcomes.append(detector.feed(sample))
    assert any(o is not None for o in outcomes)


def test_a_tap_that_drops_into_free_fall_is_not_a_click():
    spike = [Sample(i / HZ, 0.0, 0.0, 4.0 * G) for i in range(10)]
    fall = [Sample((10 + i) / HZ, 0.0, 0.0, 0.0) for i in range(50)]
    assert clicks_in(spike + fall) == 0


def test_two_clicks_inside_400ms_make_a_double_click():
    tracker = ClickTracker()
    assert [tracker.register(0.0), tracker.register(0.3), tracker.register(0.4)] == ["click", "double_click", "click"]
    assert [tracker.register(5.0), tracker.register(5.45)] == ["click", "click"]


def test_a_double_tap_stream_reaches_the_browser_as_click_then_double_click():
    client = TestClient(create_app())
    samples = hold(0.3) + tap(0.3) + hold(0.1, 0.42) + tap(0.52) + hold(0.3, 0.64)
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()
        rows = [[s.t, s.ax, s.ay, s.az, s.gx, s.gy, s.gz] for s in samples]
        for i in range(0, len(rows), 25):
            device.send_json({"samples": rows[i : i + 25]})
        seen = [viewer.receive_json()["type"], viewer.receive_json()["type"]]
    assert seen == ["click", "double_click"]


def test_a_hardware_button_frame_counts_as_a_click():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()
        device.send_json({"click": 1})
        device.send_json({"click": 1})
        assert [viewer.receive_json()["type"], viewer.receive_json()["type"]] == ["click", "double_click"]


def test_a_button_press_and_release_reach_the_browser_as_down_and_up():
    client = TestClient(create_app())
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()
        device.send_json({"button": 1})
        device.send_json({"button": 0})
        assert [viewer.receive_json(), viewer.receive_json()] == [
            {"type": "button", "down": True},
            {"type": "button", "down": False},
        ]


def test_gyro_stream_becomes_mouse_deltas_for_the_viewer():
    client = TestClient(create_app())
    rows = [[s.t, s.ax, s.ay, s.az, s.gx, s.gy, s.gz] for s in hold(0.2, gz=-1.0)]
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()
        device.send_json({"samples": rows})
        msg = viewer.receive_json()
    assert msg["type"] == "mouse" and msg["dx"] > 0 and msg["dy"] == 0
