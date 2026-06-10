// Generate slide narration audio with QVAC's on-device TTS (@qvac/sdk, supertonic).
// Reads the EN blocks from docs/narration.md → writes docs/assets/audio/s1..s10.wav.
// Run:  node tools/gen_tts.mjs
import { loadModel, textToSpeech, unloadModel, TTS_EN_SUPERTONIC_Q8_0 } from "@qvac/sdk";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SAMPLE_RATE = 44100; // supertonic output

function toWav(samples, sampleRate) {
  const data = Buffer.alloc(samples.length * 2);
  for (let i = 0; i < samples.length; i++) {
    data.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(samples[i] ?? 0))), i * 2);
  }
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + data.length, 4); h.write("WAVE", 8);
  h.write("fmt ", 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(sampleRate, 24); h.writeUInt32LE(sampleRate * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write("data", 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

const md = readFileSync(join(ROOT, "docs", "narration.md"), "utf8");
const texts = [...md.matchAll(/^\*\*EN —\*\*\s*(.+)$/gm)].map((m) => m[1].trim());
if (texts.length !== 10) {
  console.error(`Expected 10 EN narration blocks, found ${texts.length}.`);
  process.exit(1);
}

const outDir = join(ROOT, "docs", "assets", "audio");
mkdirSync(outDir, { recursive: true });

console.log("Loading QVAC supertonic TTS (downloads on first run)…");
const modelId = await loadModel({
  modelSrc: TTS_EN_SUPERTONIC_Q8_0.src,
  modelType: "tts",
  modelConfig: { ttsEngine: "supertonic", language: "en", voice: "F2", ttsSpeed: 1.0, ttsNumInferenceSteps: 5 },
  onProgress: () => process.stdout.write("."),
});
console.log(`\nModel loaded: ${modelId}`);

for (let i = 0; i < texts.length; i++) {
  const r = textToSpeech({ modelId, text: texts[i], inputType: "text", stream: false });
  const buf = await r.buffer;
  writeFileSync(join(outDir, `s${i + 1}.wav`), toWav(buf, SAMPLE_RATE));
  console.log(`✓ s${i + 1}.wav  (${buf.length} samples)`);
}

await unloadModel({ modelId });
console.log("Done → docs/assets/audio/s1..s10.wav");
process.exit(0);
