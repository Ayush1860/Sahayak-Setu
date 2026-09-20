/* Recording from the browser.

   Held down rather than toggled: a press-and-hold has an obvious end, and
   nobody is left wondering whether it is still listening. The stream is
   stopped as soon as the clip is captured, so the browser's recording
   indicator goes out immediately. */

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

export function micSupported() {
  return Boolean(
    typeof window !== "undefined" &&
      navigator.mediaDevices?.getUserMedia &&
      window.MediaRecorder
  );
}

function pickMimeType() {
  for (const type of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported?.(type)) return type;
  }
  return "";
}

export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = pickMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];

  recorder.ondataavailable = (e) => {
    if (e.data?.size) chunks.push(e.data);
  };
  recorder.start();

  return {
    async stop() {
      const done = new Promise((resolve) => {
        recorder.onstop = () => resolve();
      });
      if (recorder.state !== "inactive") recorder.stop();
      await done;
      // Release the microphone straight away.
      stream.getTracks().forEach((track) => track.stop());

      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const buffer = await blob.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buffer);
      const CHUNK = 0x8000;
      for (let i = 0; i < bytes.length; i += CHUNK) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
      }
      return {
        audio: btoa(binary),
        contentType: (recorder.mimeType || "audio/webm").split(";")[0],
        bytes: bytes.length,
      };
    },
    cancel() {
      if (recorder.state !== "inactive") recorder.stop();
      stream.getTracks().forEach((track) => track.stop());
    },
  };
}
