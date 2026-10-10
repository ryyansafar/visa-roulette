"""Paper-plane flight: a point mass with angle-of-attack aerodynamics, a damped pitch response and a banked turn.

Constants come from measured paper darts (a folded A4 sheet, about 5 g, 0.16 m span, 67 degree sweep, aspect ratio 1.1):
flight tests give speeds of 3-6 m/s, a lift coefficient of 0.17-0.19 at about 5 degrees angle of attack, a lift-to-drag
ratio near 5, and a water-tunnel lift curve that stalls near 30 degrees because the swept leading edge sheds a vortex.
The lift curve here is the leading-edge-suction analogy (Polhamus) fitted to those numbers, blended into flat-plate
behaviour after the stall.

Sources: "On the Aerodynamics of Paper Airplanes" (Lactea, UFPR); Frontiers in Mechanical Engineering 2024,
paper-airplane aspect-ratio study; Cook, "Experimental Analysis of Paper Plane Flight" (University of Queensland).

Launch speed and pitch come from whichever input threw the plane. The IMU also supplies the bank angle (roll of the board
at rest) and the flutter (how violently it tumbled in the first moments of flight).
"""

import math
from dataclasses import dataclass

G = 9.81
AIR_DENSITY = 1.2
MASS_KG = 0.005
WING_AREA_M2 = 0.023
POLHAMUS_KP, POLHAMUS_KV = 2.0, 2.54  # potential-flow and vortex lift slopes, fitted to CL 0.19 at 5 deg, 1.3 at 30 deg
STALL_DEG, STALL_END_DEG = 32.0, 45.0
FLAT_PLATE_NORMAL = 1.5  # post-stall normal-force coefficient of a low-aspect-ratio flat plate
PARASITE_DRAG = 0.022
SUCTION_LOSS = 0.85  # fraction of the lift-induced drag that tilts the force vector back
TRIM_ALPHA_DEG = 5.0
SHORT_PERIOD_PER_MS = 4.0  # pitch oscillation frequency grows with airspeed: rad/s per m/s
PITCH_DAMPING = 0.5
FLUTTER_ALPHA_DEG = 2.0  # initial angle-of-attack kick per unit of flutter
MAX_LOAD_FACTOR = 4.0
MAX_BANK_DEG = 45.0
DIHEDRAL_TURN = 0.5  # dihedral rights a banked plane, so it turns at a fraction of a coordinated turn
SPIRAL_DECAY_S = 2.5  # the bank angle relaxes back to level with this time constant
RELEASE_HEIGHT_M = 1.5
STEP_S = 0.002
MAX_FLIGHT_S = 8.0
PATH_STEP_S = 0.025
FLUTTER_FULL = 8.0
MIN_STABILITY = 0.3
MIN_SPEED = 0.5


@dataclass(frozen=True)
class Flight:
    range_m: float
    lateral_m: float
    flight_s: float
    path: tuple  # (t_s, forward_m, lateral_m, height_m) from the release to the ground
    pose: tuple = ()  # (pitch_deg, bank_deg) per path point; pitch is nose elevation, bank positive is right wing down


def _polhamus(alpha: float) -> float:
    return POLHAMUS_KP * math.sin(alpha) * math.cos(alpha) ** 2 + POLHAMUS_KV * math.sin(alpha) ** 2 * math.cos(alpha)


def _wrap(alpha: float) -> float:
    return math.atan2(math.sin(alpha), math.cos(alpha))


def _stall_blend(magnitude: float) -> float:
    """0 while the leading-edge vortex holds, 1 once the wing is a flat plate in separated flow."""
    ramp = (math.degrees(magnitude) - STALL_DEG) / (STALL_END_DEG - STALL_DEG)
    ramp = min(1.0, max(0.0, ramp))
    return ramp * ramp * (3.0 - 2.0 * ramp)


def lift_coefficient(alpha_deg: float) -> float:
    """CL for a high-sweep delta: linear at small angles, vortex-boosted to about 30 degrees, then stalled."""
    alpha = _wrap(math.radians(alpha_deg))
    magnitude = abs(alpha)
    blend = _stall_blend(magnitude)
    attached = _polhamus(min(magnitude, math.radians(STALL_DEG)))
    flat = FLAT_PLATE_NORMAL * math.sin(magnitude) * math.cos(magnitude)
    return math.copysign((1.0 - blend) * attached + blend * flat, alpha) if alpha else 0.0


def drag_coefficient(alpha_deg: float) -> float:
    magnitude = abs(_wrap(math.radians(alpha_deg)))
    blend = _stall_blend(magnitude)
    attached = PARASITE_DRAG + SUCTION_LOSS * abs(lift_coefficient(alpha_deg)) * math.tan(min(magnitude, math.radians(STALL_END_DEG)))
    flat = PARASITE_DRAG + FLAT_PLATE_NORMAL * math.sin(magnitude) ** 2
    return (1.0 - blend) * attached + blend * flat


def trim_speed() -> float:
    """Airspeed at which lift carries the weight at the trim angle of attack."""
    return math.sqrt(2.0 * MASS_KG * G / (AIR_DENSITY * WING_AREA_M2 * lift_coefficient(TRIM_ALPHA_DEG)))


def _stability(flutter: float) -> float:
    return min(1.0, max(MIN_STABILITY, 1.0 - flutter / FLUTTER_FULL))


def _display_pitch(theta: float) -> float:
    return round(max(-90.0, min(90.0, math.degrees(_wrap(theta)))), 2)


def fly(speed: float, elevation_deg: float, bank_deg: float = 0.0, flutter: float = 0.0) -> Flight:
    stability = _stability(flutter)
    bank0 = math.radians(min(max(bank_deg, -MAX_BANK_DEG), MAX_BANK_DEG))
    trim = math.radians(TRIM_ALPHA_DEG)
    damping = PITCH_DAMPING * stability
    v, gamma, psi = max(speed, MIN_SPEED), math.radians(elevation_deg), 0.0
    theta, pitch_rate = gamma + math.radians(FLUTTER_ALPHA_DEG * flutter), 0.0
    x = y = 0.0
    h = RELEASE_HEIGHT_M
    path = [(0.0, 0.0, 0.0, h)]
    pose = [(_display_pitch(theta), round(math.degrees(bank0), 2))]
    next_sample = PATH_STEP_S
    t = 0.0
    for step in range(1, int(MAX_FLIGHT_S / STEP_S) + 1):
        t = step * STEP_S
        bank = bank0 * math.exp(-t / SPIRAL_DECAY_S)
        alpha = _wrap(theta - gamma)
        alpha_deg = math.degrees(alpha)
        dynamic = 0.5 * AIR_DENSITY * v * v * WING_AREA_M2 / MASS_KG
        lift = min(max(dynamic * lift_coefficient(alpha_deg), -MAX_LOAD_FACTOR * G), MAX_LOAD_FACTOR * G)
        drag = dynamic * drag_coefficient(alpha_deg) * (1.0 + 2.0 * (1.0 - stability))
        gamma_rate = (lift * math.cos(bank) - G * math.cos(gamma)) / v
        omega = SHORT_PERIOD_PER_MS * v
        pitch_rate += (-omega * omega * (alpha - trim) - 2.0 * damping * omega * (pitch_rate - gamma_rate)) * STEP_S
        theta += pitch_rate * STEP_S
        v = max(v + (-drag - G * math.sin(gamma)) * STEP_S, MIN_SPEED)
        gamma += gamma_rate * STEP_S
        psi += DIHEDRAL_TURN * G * math.tan(bank) / v * STEP_S
        ground = v * math.cos(gamma) * STEP_S
        x += ground * math.cos(psi)
        y += ground * math.sin(psi)
        h += v * math.sin(gamma) * STEP_S
        if h <= 0.0:
            break
        if t >= next_sample:
            path.append((round(t, 3), round(x, 3), round(y, 3), round(h, 3)))
            pose.append((_display_pitch(theta), round(math.degrees(bank), 2)))
            next_sample += PATH_STEP_S
    landing = (round(t, 3), round(x, 3), round(y, 3), 0.0)
    if path[-1][0] == landing[0]:
        path[-1] = landing
    else:
        path.append(landing)
        pose.append(pose[-1])
    return Flight(range_m=math.hypot(x, y), lateral_m=y, flight_s=t, path=tuple(path), pose=tuple(pose))
