/* Webcam helpers. Frames never leave this laptop: they go to the local booth server only. */

const SCAN_INTERVAL_MS = 1600;
const MOTION = { w: 96, h: 72, pixelDelta: 38, minShare: 0.002, minSpanShare: 0.22, calmMs: 320, maxMs: 1400 };

let stream = null;

export const cameraAvailable = () => Boolean(navigator.mediaDevices?.getUserMedia);

export async function openCamera(video) {
  if (!cameraAvailable()) throw new Error("This browser has no camera access. Use a sample traveller or upload a photo.");
  if (!stream) {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1920 }, height: { ideal: 1080 }, facingMode: "environment" }, audio: false });
    } catch {
      throw new Error("The camera was blocked or is busy. Allow it in the address bar, or use a sample traveller.");
    }
  }
  video.srcObject = stream;
  video.muted = true;
  await video.play();
  return video;
}

export function closeCamera(video) {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  if (video) video.srcObject = null;
}

export function grabFrame(video, type = "image/jpeg", quality = 0.92) {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

/**
 * Try a frame every 1.6 s until `attempt(blob)` returns a truthy result.
 * Returns a stop function. `attempt` must throw or return null on a bad frame.
 */
export function scanLoop(video, attempt, { onTry = () => {}, onMiss = () => {} } = {}) {
  let live = true;
  let busy = false;
  const tick = async () => {
    if (!live) return;
    if (!busy && video.videoWidth) {
      busy = true;
      onTry();
      try {
        const blob = await grabFrame(video);
        const result = await attempt(blob);
        if (result && live) {
          live = false;
          return;
        }
        if (live) onMiss();
      } catch (err) {
        if (live) onMiss(err);
      } finally {
        busy = false;
      }
    }
    if (live) setTimeout(tick, SCAN_INTERVAL_MS);
  };
  tick();
  return () => { live = false; };
}

/**
 * Watch for a quick throwing motion in front of the camera.
 * Calls `onFlick({dx, dy, dt_ms})` in map units (1200 wide), screen up = north, as if the camera were a mirror.
 */
export function watchThrow(video, onFlick, { mapWidth = 1200, onMotion = () => {} } = {}) {
  const { w, h } = MOTION;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let previous = null;
  let track = [];
  let lastMoveAt = 0;
  let live = true;

  const finish = () => {
    const spanX = Math.abs(track.at(-1).x - track[0].x);
    const spanY = Math.abs(track.at(-1).y - track[0].y);
    const elapsed = track.at(-1).t - track[0].t;
    if (track.length >= 3 && Math.max(spanX / w, spanY / h) >= MOTION.minSpanShare && elapsed > 0) {
      onFlick({ dx: -((track.at(-1).x - track[0].x) / w) * mapWidth, dy: ((track.at(-1).y - track[0].y) / h) * ((mapWidth * h) / w), dt_ms: elapsed });
    }
    track = [];
  };

  const frame = () => {
    if (!live) return;
    if (video.videoWidth) {
      ctx.drawImage(video, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h).data;
      const gray = new Uint8Array(w * h);
      for (let i = 0; i < gray.length; i++) gray[i] = (data[i * 4] * 3 + data[i * 4 + 1] * 6 + data[i * 4 + 2]) / 10;
      if (previous) {
        let count = 0;
        let sx = 0;
        let sy = 0;
        let any = 0;
        for (let i = 0; i < gray.length; i++) {
          if (gray[i] !== previous[i]) any++;
          if (Math.abs(gray[i] - previous[i]) > MOTION.pixelDelta) {
            count++;
            sx += i % w;
            sy += Math.floor(i / w);
          }
        }
        const repeated = any === 0; // the camera delivered the same frame twice: no new information
        const now = performance.now();
        if (!repeated) {
          const moving = count / gray.length >= MOTION.minShare;
          onMotion(moving);
          if (moving) {
            lastMoveAt = now;
            track.push({ x: sx / count, y: sy / count, t: now });
            if (now - track[0].t > MOTION.maxMs) track.shift();
          }
        }
        if (track.length && now - lastMoveAt >= MOTION.calmMs) {
          onMotion(false);
          finish();
        }
      }
      previous = gray;
    }
    setTimeout(frame, 40);
  };
  frame();
  return () => { live = false; };
}
