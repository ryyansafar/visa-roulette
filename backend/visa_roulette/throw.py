"""Turn motion into a throw: IMU samples, a mouse flick or a single switch all become one ThrowResult.

Heading is clockwise from "forward" (0 = north on the map, 90 = east). For the IMU the device x axis is
forward and z is up when the board sits flat before the throw. The range is ballistic and then scaled to
the globe: one metre of throw is GLOBE_KM_PER_M kilometres, capped at half the planet.
"""

import dataclasses
import math
from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

G = 9.81
GLOBE_KM_PER_M = 1500.0
MAX_DISTANCE_KM = 19_000.0

LAUNCH_READING = 20.0  # m/s^2 total reading that starts a throw
FREEFALL_READING = 4.0  # below this the board is no longer in the hand
FREEFALL_HOLD_S = 0.03
MAX_PUSH_S = 0.5  # a push longer than this was a shake, not a throw
REST_S = 0.5
REST_TOLERANCE = 2.0
MIN_SPEED, MAX_SPEED = 2.5, 25.0
LANDED_QUIET_S = 0.3
MAX_FLIGHT_S = 4.0
SWITCH_SPEED_RANGE = (3.0, 11.0)
FLICK_FULL_POWER_PX_PER_MS = 3.0
FLICK_MIN_PX = 20.0
DEFAULT_ELEVATION_DEG = 40.0


class ThrowError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Sample:
    t: float
    ax: float
    ay: float
    az: float

    @property
    def vector(self) -> np.ndarray:
        return np.array([self.ax, self.ay, self.az])

    @property
    def magnitude(self) -> float:
        return float(np.linalg.norm(self.vector))


@dataclass(frozen=True)
class ThrowResult:
    speed_mps: float
    elevation_deg: float
    heading_deg: float
    range_m: float
    distance_km: float
    source: str
    flight_s: float = 0.0


@dataclass(frozen=True)
class ThrowRejected:
    code: str
    message: str


Outcome = Union[ThrowResult, ThrowRejected, None]


def _result(speed: float, elevation_deg: float, heading_deg: float, source: str) -> ThrowResult:
    effective = min(max(elevation_deg, 5.0), 85.0)
    range_m = speed**2 * math.sin(math.radians(2 * effective)) / G
    return ThrowResult(
        speed_mps=speed,
        elevation_deg=elevation_deg,
        heading_deg=heading_deg % 360.0,
        range_m=range_m,
        distance_km=min(range_m * GLOBE_KM_PER_M, MAX_DISTANCE_KM),
        source=source,
    )


def throw_from_power(heading_deg: float, power: float) -> ThrowResult:
    """Single-switch input: one press locks the sweeping heading, the next locks the power meter."""
    if not (0.0 <= heading_deg < 360.0):
        raise ThrowError("bad_heading", "Heading must be from 0 up to 360 degrees.")
    if not (0.0 <= power <= 1.0):
        raise ThrowError("bad_power", "Power must be between 0 and 1.")
    low, high = SWITCH_SPEED_RANGE
    return _result(low + (high - low) * power, DEFAULT_ELEVATION_DEG, heading_deg, "switch")


def throw_from_flick(dx: float, dy: float, dt_ms: float) -> ThrowResult:
    """Mouse or touch flick: screen up is north, speed of the flick sets the power."""
    length = math.hypot(dx, dy)
    if dt_ms <= 0 or length < FLICK_MIN_PX:
        raise ThrowError("not_a_flick", "Flick the plane with a quick, longer swipe.")
    power = min(1.0, (length / dt_ms) / FLICK_FULL_POWER_PX_PER_MS)
    heading = math.degrees(math.atan2(dx, -dy)) % 360.0
    low, high = SWITCH_SPEED_RANGE
    return _result(low + (high - low) * power, DEFAULT_ELEVATION_DEG, heading, "flick")


def _rest_gravity(history: list, before_t: float) -> Optional[np.ndarray]:
    rest = [s for s in history if before_t - REST_S <= s.t < before_t and abs(s.magnitude - G) < REST_TOLERANCE]
    if len(rest) < 5:
        return None
    return np.mean([s.vector for s in rest], axis=0)


def _launch(history: list, push: list, release_t: float) -> Union[ThrowResult, ThrowRejected]:
    gravity = _rest_gravity(history, push[0].t)
    if gravity is None:
        return ThrowRejected("no_rest", "Hold the board still for a moment before you throw.")
    velocity = np.zeros(3)
    times = [s.t for s in push] + [release_t]
    for sample, nxt in zip(push, times[1:]):
        velocity += (sample.vector - gravity) * (nxt - sample.t)
    speed = float(np.linalg.norm(velocity))
    if speed < MIN_SPEED:
        return ThrowRejected("too_weak", "That throw was too gentle. Throw it harder.")
    up = gravity / np.linalg.norm(gravity)
    forward = np.array([1.0, 0.0, 0.0]) - up[0] * up
    if np.linalg.norm(forward) < 0.25:
        return ThrowRejected("mount_angle", "Mount the board flat so its x axis points forward.")
    forward /= np.linalg.norm(forward)
    right = np.cross(up, forward)
    horizontal = velocity - float(velocity @ up) * up
    if np.linalg.norm(horizontal) < 0.5:
        return ThrowRejected("straight_up", "Throw it forward, not straight up.")
    elevation = math.degrees(math.asin(float(np.clip(velocity @ up / speed, -1.0, 1.0))))
    heading = math.degrees(math.atan2(float(horizontal @ right), float(horizontal @ forward)))
    return _result(min(speed, MAX_SPEED), elevation, heading, "imu")


class ThrowDetector:
    """Streaming state machine: rest, push, flight, landing. Emits one outcome per throw."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._state = "idle"
        self._history: list = []
        self._push: list = []
        self._low_since: Optional[float] = None
        self._pending: Optional[ThrowResult] = None
        self._release_t = 0.0
        self._quiet_since: Optional[float] = None

    def feed(self, sample: Sample) -> Outcome:
        if self._state == "idle":
            return self._idle(sample)
        if self._state == "push":
            return self._pushing(sample)
        return self._flying(sample)

    def flush(self) -> Outcome:
        """End of data: a throw still in the air counts as landed now."""
        if self._state != "flight" or self._pending is None:
            return None
        return self._complete(self._release_t + self._pending.flight_s)

    def _idle(self, sample: Sample) -> Outcome:
        self._history = [s for s in self._history if sample.t - s.t <= 1.5] + [sample]
        if sample.magnitude > LAUNCH_READING:
            start = len(self._history) - 1
            while start > 0 and abs(self._history[start - 1].magnitude - G) > REST_TOLERANCE:
                start -= 1
            self._push = self._history[start:]
            self._history = self._history[:start]
            self._state, self._low_since = "push", None
        return None

    def _pushing(self, sample: Sample) -> Outcome:
        if sample.t - self._push[0].t > MAX_PUSH_S:
            self._reset()
            return None
        if sample.magnitude >= FREEFALL_READING:
            self._push.append(sample)
            self._low_since = None
            return None
        self._low_since = sample.t if self._low_since is None else self._low_since
        if sample.t - self._low_since < FREEFALL_HOLD_S:
            return None
        outcome = _launch(self._history, self._push, self._low_since)
        if isinstance(outcome, ThrowRejected):
            self._reset()
            return outcome
        self._pending, self._release_t = outcome, self._low_since
        self._state, self._quiet_since = "flight", None
        return None

    def _flying(self, sample: Sample) -> Outcome:
        in_air = sample.t - self._release_t
        if sample.magnitude > LAUNCH_READING and in_air > FREEFALL_HOLD_S:
            return self._complete(sample.t)
        if abs(sample.magnitude - G) < 1.5 and in_air > 0.2:
            self._quiet_since = sample.t if self._quiet_since is None else self._quiet_since
            if sample.t - self._quiet_since >= LANDED_QUIET_S:
                return self._complete(self._quiet_since)
        else:
            self._quiet_since = None
        return self._complete(sample.t) if in_air >= MAX_FLIGHT_S else None

    def _complete(self, landed_t: float) -> ThrowResult:
        result = dataclasses.replace(self._pending, flight_s=max(landed_t - self._release_t, 0.0))
        self._reset()
        return result


def analyze_throw(samples: list) -> ThrowResult:
    """Batch form for a recorded window of samples."""
    detector = ThrowDetector()
    for sample in samples:
        outcome = detector.feed(sample)
        if outcome is not None:
            break
    else:
        outcome = detector.flush()
    if isinstance(outcome, ThrowResult):
        return outcome
    if isinstance(outcome, ThrowRejected):
        raise ThrowError(outcome.code, outcome.message)
    raise ThrowError("no_throw", "No throw found. Hold still, throw, and let it land.")
