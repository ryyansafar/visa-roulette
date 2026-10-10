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
) -> list:
    """Rest, a constant-acceleration push to `speed`, free flight, one impact spike, then rest."""
    dt = 1.0 / hz
    elev, head = math.radians(elevation_deg), math.radians(heading_deg)
    direction = (math.cos(elev) * math.cos(head), math.cos(elev) * math.sin(head), math.sin(elev))
    rows, t = [], 0.0

    def emit(count: int, reading) -> None:
        nonlocal t
        for _ in range(count):
            rows.append((round(t, 6), *reading))
            t += dt

    emit(round(rest_s * hz), (0.0, 0.0, G))
    if speed <= 0 or push_s <= 0:
        emit(round((flight_s + land_s) * hz), (0.0, 0.0, G))
        return rows
    push = speed / push_s
    emit(round(push_s * hz), (push * direction[0], push * direction[1], push * direction[2] + G))
    emit(round(flight_s * hz), (0.0, 0.0, 0.0))
    emit(1, (0.0, 0.0, 4.5 * G))
    emit(round(land_s * hz), (0.0, 0.0, G))
    return rows
