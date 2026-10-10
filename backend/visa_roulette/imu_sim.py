"""Synthetic IMU traces: a stand-in ESP32 for tests and for rehearsing without hardware.

Device frame: x forward, y right, z up. Samples are accelerometer readings in m/s^2
(specific force, so a board at rest reads +g on z and a falling board reads ~0).
"""

import math

G = 9.81


def synth_throw(
    speed: float,
    elevation_deg: float,
    heading_deg: float,
    hz: int = 200,
    rest_s: float = 0.5,
    push_s: float = 0.08,
    flight_s: float = 0.6,
    land_s: float = 0.5,
    roll_deg: float = 0.0,
    tumble: float = 0.0,
    gyro: bool = False,
    spin_rad_s: float = 0.0,
) -> list:
    """Rest, a constant-acceleration push to `speed`, free flight, one impact spike, then rest.

    roll_deg tilts the board at rest (positive = right wing down). tumble is the steady reading (m/s^2) of a
    board that spins in flight, which starts 50 ms after release so the release itself still looks like free fall.
    With gyro=True every row gains gx, gy, gz in rad/s (an MPU-6050 stream); spin_rad_s is the in-flight spin rate.
    """
    dt = 1.0 / hz
    roll = math.radians(roll_deg)
    gravity = (0.0, -G * math.sin(roll), G * math.cos(roll))
    elev, head = math.radians(elevation_deg), math.radians(heading_deg)
    direction = (math.cos(elev) * math.cos(head), math.cos(elev) * math.sin(head), math.sin(elev))
    rows, t = [], 0.0

    def emit(count: int, reading, rates=(0.0, 0.0, 0.0)) -> None:
        nonlocal t
        for _ in range(count):
            rows.append((round(t, 6), *reading, *(rates if gyro else ())))
            t += dt

    emit(round(rest_s * hz), gravity)
    if speed <= 0 or push_s <= 0:
        emit(round((flight_s + land_s) * hz), gravity)
        return rows
    push = speed / push_s
    emit(round(push_s * hz), (push * direction[0] + gravity[0], push * direction[1] + gravity[1], push * direction[2] + gravity[2]))
    quiet = round(0.05 * hz) if tumble > 0 or spin_rad_s > 0 else round(flight_s * hz)
    emit(quiet, (0.0, 0.0, 0.0))
    for i in range(round(flight_s * hz) - quiet):
        emit(1, (tumble * math.cos(i * 0.9), tumble * math.sin(i * 0.9), 0.0), (spin_rad_s * math.cos(i * 0.9), spin_rad_s * math.sin(i * 0.9), 0.0))
    emit(1, (0.0, 0.0, 4.5 * G))
    emit(round(land_s * hz), gravity)
    return rows
