// Copies the files the camera demo needs into public/ so the website serves
// them itself (no third-party CDN at runtime):
//   - MediaPipe Tasks Vision WebAssembly files (Apache-2.0, from node_modules)
//   - the MediaPipe Face Landmarker model (Apache-2.0)
// Runs automatically before `npm run dev` and `npm run build`. Output is git-ignored.
import { copyFileSync, existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const site = join(here, "..");
const wasmFrom = join(site, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const wasmTo = join(site, "public", "vendor", "mediapipe", "wasm");
const modelTo = join(site, "public", "models", "face_landmarker.task");
const repoModel = join(site, "..", "models", "face_landmarker.task"); // same file the desktop app uses
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

mkdirSync(wasmTo, { recursive: true });
for (const file of readdirSync(wasmFrom)) copyFileSync(join(wasmFrom, file), join(wasmTo, file));

mkdirSync(dirname(modelTo), { recursive: true });
if (!existsSync(modelTo)) {
  if (existsSync(repoModel)) {
    copyFileSync(repoModel, modelTo);
  } else {
    console.log("Downloading the MediaPipe face model (one time)…");
    const response = await fetch(MODEL_URL);
    if (!response.ok) throw new Error(`Model download failed: HTTP ${response.status}`);
    writeFileSync(modelTo, Buffer.from(await response.arrayBuffer()));
  }
}
console.log("Camera demo assets ready in public/vendor and public/models.");
