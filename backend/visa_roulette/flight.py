"""Paper-plane flight: a point mass with lift, drag and a banked turn, integrated from the release.

Launch speed and pitch come from whichever input threw the plane. The IMU also supplies the bank angle
(roll of the board at rest) and the flutter (how violently it tumbled in the first moments of flight).
Constants describe a folded A4 dart: about 5 g, 0.03 m^2 of wing, a glide ratio of roughly 4.5.
"""

import math
from dataclasses import dataclass

G = 9.81
AIR_DENSITY = 1.2
MASS_KG = 0.005
WING_AREA_M2 = 0.03
TRIM_LIFT = 0.45
PARASITE_DRAG = 0.04
INDUCED_DRAG = 0.40
MAX_LOAD_FACTOR = 4.0
MAX_BANK_DEG = 45.0
DIHEDRAL_TURN = 0.3  # dihedral rights a banked plane, so it turns at a fraction of a coordinated turn
STALL_START_DEG, STALL_FULL_DEG = 50.0, 80.0
RELEASE_HEIGHT_M = 1.5
STEP_S = 0.002
MAX_FLIGHT_S = 8.0
PATH_STEP_S = 0.05
FLUTTER_FULL = 8.0
MIN_STABILITY = 0.3


@dataclass(frozen=True)
class Flight:
    range_m: float
    lateral_m: float
    flight_s: float
    path: tuple  # (t_s, forward_m, lateral_m, height_m) from the release to the ground


def _stability(flutter: float) -> float:
    return min(1.0, max(MIN_STABILITY, 1.0 - flutter / FLUTTER_FULL))


def _stall(gamma: float) -> float:
    """Lift left once the nose is pitched this steeply: a plane thrown near-vertical stalls and drops."""
    steep = abs(math.degrees(gamma))
    return min(1.0, max(0.0, (STALL_FULL_DEG - steep) / (STALL_FULL_DEG - STALL_START_DEG)))


def _accelerations(speed: float, stability: float) -> tuple:
    """Lift and drag as accelerations (m/s^2). A tumbling plane keeps less lift and more drag."""
    dynamic = 0.5 * AIR_DENSITY * speed * speed * WING_AREA_M2 / MASS_KG
    lift_coefficient = TRIM_LIFT * stability
    drag_coefficient = (PARASITE_DRAG + INDUCED_DRAG * lift_coefficient**2) * (1.0 + 2.0 * (1.0 - stability))
    return dynamic * lift_coefficient, dynamic * drag_coefficient


def fly(speed: float, elevation_deg: float, bank_deg: float = 0.0, flutter: float = 0.0) -> Flight:
    stability = _stability(flutter)
    bank = math.radians(min(max(bank_deg, -MAX_BANK_DEG), MAX_BANK_DEG))
    v, gamma, psi = max(speed, 0.5), math.radians(elevation_deg), 0.0
    x = y = 0.0
    h, t = RELEASE_HEIGHT_M, 0.0
    path = [(0.0, 0.0, 0.0, h)]
    next_sample = PATH_STEP_S
    while h > 0.0 and t < MAX_FLIGHT_S:
        lift, drag = _accelerations(v, stability)
        lift = min(lift, MAX_LOAD_FACTOR * G) * _stall(gamma)
        v = max(v + (-drag - G * math.sin(gamma)) * STEP_S, 0.5)
        gamma += (lift * math.cos(bank) - G * math.cos(gamma)) / v * STEP_S
        psi += DIHEDRAL_TURN * G * math.tan(bank) / v * STEP_S
        ground = v * math.cos(gamma) * STEP_S
        x += ground * math.cos(psi)
        y += ground * math.sin(psi)
        h += v * math.sin(gamma) * STEP_S
        t += STEP_S
        if t >= next_sample:
            path.append((round(t, 3), round(x, 3), round(y, 3), round(max(h, 0.0), 3)))
            next_sample += PATH_STEP_S
    path.append((round(t, 3), round(x, 3), round(y, 3), 0.0))
    return Flight(range_m=math.hypot(x, y), lateral_m=y, flight_s=t, path=tuple(path))
