/* Webcam helpers. Frames never leave this laptop: they go to the local booth server only. */

import { TRACK, createRecorder, measureBlob } from "./throwtrack.js";

const SCAN_INTERVAL_MS = 1600;

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
 * Watch for a plane thrown straight at the camera. Calls `onTrack([{t_ms, cx, cy, w}])` when the motion settles;
 * the server reads speed, heading and launch angle from how the blob grows and drifts.
 */
export function watchThrow(video, onTrack, { onMotion = () => {} } = {}) {
  const { w, h } = TRACK;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const recorder = createRecorder();
  let previous = null;
  let live = true;

  const frame = () => {
    if (!live) return;
    if (video.videoWidth) {
      ctx.drawImage(video, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h).data;
      const gray = new Uint8Array(w * h);
      for (let i = 0; i < gray.length; i++) gray[i] = (data[i * 4] * 3 + data[i * 4 + 1] * 6 + data[i * 4 + 2]) / 10;
      const now = performance.now();
      if (previous) {
        const { state, point } = measureBlob(gray, previous);
        if (state !== "repeat") {
          onMotion(state === "moving");
          if (state === "moving") recorder.push(point, now);
        }
        const track = recorder.poll(now);
        if (track) {
          onMotion(false);
          onTrack(track);
        }
      }
      previous = gray;
    }
    setTimeout(frame, 16);
  };
  frame();
  return () => { live = false; };
}
