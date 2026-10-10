import math

import pytest
from fastapi.testclient import TestClient

from visa_roulette.api import create_app
from visa_roulette.camera_throw import FOV_DEG, PLANE_SIZE_M, throw_from_camera
from visa_roulette.throw import ThrowError

FOCAL = 0.5 / math.tan(math.radians(FOV_DEG) / 2)
client = TestClient(create_app())


def track(speed=6.0, start=3.5, lateral=0.0, climb=0.0, frames=8, hz=30, height=0.0):
    """What the camera sees of a plane flying at it: world metres (z from the camera, x to the player's right, y up)."""
    rows = []
    for i in range(frames):
        t = i / hz
        z = start - speed * t
        x = lateral * t
        y = height + climb * t
        rows.append({"t_ms": t * 1000.0, "cx": 0.5 + x * FOCAL / z, "cy": 0.5 - y * FOCAL / z, "w": PLANE_SIZE_M * FOCAL / z})
    return rows


def test_a_plane_thrown_straight_at_the_camera_reads_its_speed_and_points_north():
    r = throw_from_camera(track(speed=6.0))
    assert r.source == "camera"
    assert r.speed_mps == pytest.approx(6.0, rel=0.1)
    assert r.launch_heading_deg == pytest.approx(0.0, abs=2) or r.launch_heading_deg > 358


def test_a_harder_throw_at_the_camera_goes_further():
    assert throw_from_camera(track(speed=9.0)).distance_km > throw_from_camera(track(speed=4.0)).distance_km


def test_drifting_to_the_players_right_aims_east_of_north():
    r = throw_from_camera(track(speed=6.0, lateral=1.5))
    assert 5.0 < r.launch_heading_deg < 60.0


def test_drifting_left_aims_west_of_north():
    r = throw_from_camera(track(speed=6.0, lateral=-1.5))
    assert 300.0 < r.launch_heading_deg < 355.0


def test_a_rising_plane_has_a_higher_launch_angle_than_a_level_one():
    level = throw_from_camera(track(speed=6.0, climb=0.0, height=0.2))
    rising = throw_from_camera(track(speed=6.0, climb=3.0, height=0.2))
    assert rising.elevation_deg > level.elevation_deg + 10


def test_a_plane_that_is_not_growing_is_not_a_throw_at_the_camera():
    across = [{"t_ms": i * 33.0, "cx": 0.2 + i * 0.08, "cy": 0.5, "w": 0.08} for i in range(8)]
    with pytest.raises(ThrowError) as err:
        throw_from_camera(across)
    assert err.value.code == "not_toward_camera"


def test_a_plane_moving_away_is_not_a_throw_at_the_camera():
    with pytest.raises(ThrowError) as err:
        throw_from_camera(track(speed=-4.0, start=1.0))
    assert err.value.code == "not_toward_camera"


def test_too_few_frames_is_not_enough_to_judge():
    with pytest.raises(ThrowError) as err:
        throw_from_camera(track(frames=2))
    assert err.value.code == "too_short"


def test_a_feeble_toss_is_rejected():
    with pytest.raises(ThrowError) as err:
        throw_from_camera(track(speed=0.8, start=1.5, frames=8, hz=10))
    assert err.value.code == "too_weak"


def test_the_endpoint_returns_a_throw_with_a_flight_path():
    out = client.post("/api/throw/camera", json={"track": track(speed=6.0)})
    assert out.status_code == 200
    body = out.json()
    assert body["source"] == "camera" and body["distance_km"] > 0 and len(body["path"]) > 5


def test_the_endpoint_explains_a_throw_that_is_not_at_the_camera():
    across = [{"t_ms": i * 33.0, "cx": 0.2 + i * 0.08, "cy": 0.5, "w": 0.08} for i in range(8)]
    out = client.post("/api/throw/camera", json={"track": across})
    assert out.status_code == 422 and out.json()["detail"]["code"] == "not_toward_camera"


@pytest.mark.parametrize("bad", [{"track": []}, {"track": [{"t_ms": 0, "cx": 2, "cy": 0.5, "w": 0.1}] * 4}, {"track": [{"t_ms": 0, "cx": 0.5, "cy": 0.5, "w": 0}] * 4}])
def test_the_endpoint_rejects_malformed_tracks(bad):
    assert client.post("/api/throw/camera", json=bad).status_code == 422
