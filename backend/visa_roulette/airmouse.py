"""Air mouse: turn the board's gyro into cursor deltas and a sharp tap into a click.

Board frame: x forward, y right, z up when flat. Yaw (gz, rad/s) moves the cursor sideways and pitch (gy)
moves it up and down. A click is a short accelerometer spike (a tap on the board); a throw is a long push
that ends in free fall, so the two never overlap: a spike counts as a click only if it ends back at a
normal reading in under CLICK_MAX_S.
"""

from dataclasses import dataclass

from visa_roulette.throw import FREEFALL_HOLD_S, FREEFALL_READING, G, Sample

GAIN_PX_PER_RAD = 900.0
DEADZONE_RAD_S = 0.06  # about 3.5 deg/s: below this is bias and sensor noise
SMOOTHING = 0.35  # weight of the newest sample in the low-pass
MAX_JUMP_PX = 120.0
EMIT_EVERY_S = 1 / 30
MOTION_ARTIFACT = 6.0  # |reading - g| above this means a tap or throw, not a steady hand

CLICK_SPIKE = 2.5 * G
CLICK_MAX_S = 0.08
CLICK_REFRACTORY_S = 0.07  # a tap rings; ignore the echo
THROW_MUTE_S = 1.0  # the landing thud after a throw is not a click
CLICK_SETTLE = 15.0  # a reading below this ends the spike
DOUBLE_CLICK_S = 0.4


@dataclass(frozen=True)
class MouseDelta:
    dx: float
    dy: float


class MouseStepper:
    """Smoothed, dead-zoned gyro to throttled (dx, dy) pixel deltas."""

    def __init__(self, gain: float = GAIN_PX_PER_RAD, deadzone: float = DEADZONE_RAD_S) -> None:
        self._gain, self._deadzone = gain, deadzone
        self._yaw = self._pitch = 0.0
        self._acc_x = self._acc_y = 0.0
        self._last_t: float | None = None
        self._emitted_t: float | None = None

    def reset(self) -> None:
        self._yaw = self._pitch = self._acc_x = self._acc_y = 0.0

    def feed(self, sample: Sample) -> MouseDelta | None:
        dt = 0.0 if self._last_t is None else min(max(sample.t - self._last_t, 0.0), 0.05)
        self._last_t = sample.t
        if self._emitted_t is None:
            self._emitted_t = sample.t
        if abs(sample.magnitude - G) > MOTION_ARTIFACT:
            self.reset()
            return None
        self._yaw += SMOOTHING * (sample.gz - self._yaw)
        self._pitch += SMOOTHING * (sample.gy - self._pitch)
        self._acc_x -= _dead(self._yaw, self._deadzone) * self._gain * dt
        self._acc_y += _dead(self._pitch, self._deadzone) * self._gain * dt
        if sample.t - self._emitted_t < EMIT_EVERY_S:
            return None
        self._emitted_t = sample.t
        delta = MouseDelta(_clamp(self._acc_x), _clamp(self._acc_y))
        self._acc_x = self._acc_y = 0.0
        return delta if (delta.dx or delta.dy) else None


def _dead(rate: float, zone: float) -> float:
    return 0.0 if abs(rate) < zone else rate - zone * (1 if rate > 0 else -1)


def _clamp(value: float) -> float:
    return round(max(-MAX_JUMP_PX, min(MAX_JUMP_PX, value)), 1)


class ClickDetector:
    """A spike above CLICK_SPIKE that settles within CLICK_MAX_S and stays out of free fall is one click."""

    def __init__(self) -> None:
        self._state = "idle"
        self._since = 0.0
        self._quiet_after = -1.0

    def mute_until(self, t: float) -> None:
        self._state, self._quiet_after = "idle", max(self._quiet_after, t)

    def feed(self, sample: Sample) -> bool:
        t, mag = sample.t, sample.magnitude
        if self._state == "settling":
            return self._settling(t, mag)
        if mag >= CLICK_SETTLE:
            self._high(t, mag)
        elif self._state == "spike" and t - self._since <= CLICK_MAX_S:
            self._state, self._since = "settling", t
            return self._settling(t, mag)
        else:
            self._state = "idle"
        return False

    def _high(self, t: float, mag: float) -> None:
        if self._state == "idle" and mag > CLICK_SPIKE and t >= self._quiet_after:
            self._state, self._since = "spike", t
        elif self._state == "spike" and t - self._since > CLICK_MAX_S:
            self._state = "sustained"

    def _settling(self, t: float, mag: float) -> bool:
        if mag < FREEFALL_READING or mag >= CLICK_SETTLE:
            self._state = "idle"
            return False
        if t - self._since < FREEFALL_HOLD_S:
            return False
        self._state, self._quiet_after = "idle", t + CLICK_REFRACTORY_S
        return True


class ClickTracker:
    """Pairs clicks: the second one inside DOUBLE_CLICK_S becomes a double click."""

    def __init__(self, window: float = DOUBLE_CLICK_S) -> None:
        self._window = window
        self._last: float | None = None

    def register(self, now: float) -> str:
        if self._last is not None and now - self._last <= self._window:
            self._last = None
            return "double_click"
        self._last = now
        return "click"
