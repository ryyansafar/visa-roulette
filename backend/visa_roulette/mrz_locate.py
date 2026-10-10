"""Locate the machine-readable zone in a messy frame (classic morphology approach)."""


from PIL import Image

try:
    import cv2
    import numpy as np
except ImportError:  # OpenCV is optional; the scanner falls back to fixed crops
    cv2 = None
    np = None

_WORK_WIDTH = 700


def opencv_available() -> bool:
    return cv2 is not None


def locate_mrz(image: Image.Image) -> Image.Image | None:
    """Return a padded crop around the lowest wide text block, or None."""
    if cv2 is None:
        return None
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    ratio = _WORK_WIDTH / gray.shape[1]
    small = cv2.GaussianBlur(cv2.resize(gray, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA), (3, 3), 0)

    rect = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    square = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    gradient = np.abs(cv2.Sobel(cv2.morphologyEx(small, cv2.MORPH_BLACKHAT, rect), cv2.CV_32F, 1, 0, ksize=-1))
    low, high = float(gradient.min()), float(gradient.max())
    if high - low < 1e-6:
        return None
    gradient = (255 * (gradient - low) / (high - low)).astype("uint8")
    gradient = cv2.morphologyEx(gradient, cv2.MORPH_CLOSE, rect)
    binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    binary = cv2.erode(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, square), None, iterations=4)

    best = None
    for contour in cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]:
        x, y, w, h = cv2.boundingRect(contour)
        if h == 0 or w / h < 5 or w / small.shape[1] < 0.6:
            continue
        if best is None or y > best[1]:
            best = (x, y, w, h)
    if best is None:
        return None

    x, y, w, h = (int(v / ratio) for v in best)
    pad_x, pad_y = int(w * 0.03), h
    box = (max(x - pad_x, 0), max(y - pad_y, 0), min(x + w + pad_x, image.width), min(y + h + pad_y, image.height))
    return image.crop(box)
