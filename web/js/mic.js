// Mic recording (speech in) and amplitude-driven playback (speech out -> mouth shape).
// Both local/offline: recording uses MediaRecorder, playback analysis uses Web Audio's AnalyserNode.
// No audio is kept after a call returns - callers get a Blob or a promise, nothing is cached here.

let recorder = null;
let chunks = [];

export function micAvailable() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
}

export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.start();
}

export function stopRecording() {
  return new Promise((resolve) => {
    if (!recorder) return resolve(null);
    recorder.addEventListener("stop", () => {
      recorder.stream.getTracks().forEach((track) => track.stop());
      resolve(new Blob(chunks, { type: "audio/webm" }));
      recorder = null;
    }, { once: true });
    recorder.stop();
  });
}

let audioCtx = null;

// Plays `blob` and calls onLevel(0..1) on every animation frame while it plays, so the caller can
// drive a mouth shape from real amplitude instead of a fake timer. Resolves when playback ends.
export async function playWithLevel(blob, onLevel) {
  audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
  const buffer = await audioCtx.decodeAudioData(await blob.arrayBuffer());
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  const data = new Uint8Array(analyser.frequencyBinCount);
  source.connect(analyser);
  analyser.connect(audioCtx.destination);

  let raf = null;
  const tick = () => {
    analyser.getByteTimeDomainData(data);
    const rms = Math.sqrt(data.reduce((sum, v) => sum + ((v - 128) / 128) ** 2, 0) / data.length);
    onLevel(Math.min(1, rms * 4));
    raf = requestAnimationFrame(tick);
  };

  return new Promise((resolve) => {
    source.onended = () => { cancelAnimationFrame(raf); onLevel(0); resolve(); };
    source.start();
    tick();
  });
}
