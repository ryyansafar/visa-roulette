"""Read a throw made straight at the camera.

The browser tracks the moving blob frame by frame and sends (time, centre, size). A plane flying at the lens
grows in the image: size is inversely proportional to distance, so the growth gives the approach speed, the
sideways drift gives the heading and the climb gives the launch angle. Heading 0 is straight at the camera
(north on the map) and a drift to the player's right turns it east.
"""

import math

import numpy as np

from visa_roulette.throw import MIN_SPEED, MAX_SPEED, ThrowError, ThrowResult, make_result

FOV_DEG = 60.0
PLANE_SIZE_M = 0.12  # side of a square with the same area as a folded plane seen from the front or the back
MIN_POINTS = 4
MIN_SPAN_S = 0.06
MIN_GROWTH = 1.3
MAX_ELEVATION_DEG = 70.0
FOCAL = 0.5 / math.tan(math.radians(FOV_DEG) / 2)  # focal length in frame widths


def _slope(xs: np.ndarray, ys: np.ndarray) -> float:
    spread = float(np.var(xs))
    return 0.0 if spread < 1e-12 else float(np.cov(xs, ys, bias=True)[0, 1] / spread)


def throw_from_camera(track: list) -> ThrowResult:
    points = sorted(track, key=lambda p: p["t_ms"])
    if len(points) < MIN_POINTS or (points[-1]["t_ms"] - points[0]["t_ms"]) / 1000.0 < MIN_SPAN_S:
        raise ThrowError("too_short", "The camera lost the plane. Throw it nose first, straight at the lens.")
    t = np.array([p["t_ms"] for p in points]) / 1000.0
    width = np.array([p["w"] for p in points])
    z = FOCAL * PLANE_SIZE_M / width
    x = (np.array([p["cx"] for p in points]) - 0.5) * z / FOCAL
    y = (0.5 - np.array([p["cy"] for p in points])) * z / FOCAL
    approach = -_slope(t, z)
    if approach <= 0.0 or width[-1] / width[0] < MIN_GROWTH:
        raise ThrowError("not_toward_camera", "Throw the plane straight at the camera, not across it.")
    if approach < MIN_SPEED:
        raise ThrowError("too_weak", "That throw was too gentle. Throw it harder.")
    along = -z  # distance travelled towards the camera grows as z shrinks
    heading = math.degrees(math.atan(_slope(along, x)))
    elevation = min(max(math.degrees(math.atan(_slope(along, y))), 0.0), MAX_ELEVATION_DEG)
    return make_result(min(approach, MAX_SPEED), elevation, heading, "camera")
