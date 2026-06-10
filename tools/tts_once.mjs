// Generate a single WAV from text read on stdin, write to argv[2].
// Used by bot/sdr_broadcast.py for cross-platform TTS (no macOS say required).
//
// Usage:
//   echo "text to speak" | node tools/tts_once.mjs /tmp/output.wav
//   node tools/tts_once.mjs /tmp/output.wav    # then type / pipe text on stdin
//
import { loadModel, textToSpeech, unloadModel, TTS_EN_SUPERTONIC_Q8_0 } from "@qvac/sdk";
import { writeFileSync } from "fs";

const outPath = process.argv[2];
if (!outPath) {
  console.error("Usage: echo 'text' | node tts_once.mjs <output.wav>");
  process.exit(1);
}

// Read text from stdin
let text = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) text += chunk;
text = text.trim();

if (!text) {
  console.error("tts_once: empty input on stdin");
  process.exit(1);
}

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

const SAMPLE_RATE = 44100;

process.stderr.write("tts_once: loading QVAC TTS model…\n");
const modelId = await loadModel({
  modelSrc: TTS_EN_SUPERTONIC_Q8_0.src,
  modelType: "tts",
  modelConfig: { ttsEngine: "supertonic", language: "en", voice: "F2", ttsSpeed: 1.0, ttsNumInferenceSteps: 5 },
  onProgress: () => process.stderr.write("."),
});
process.stderr.write(`\ntts_once: model loaded (${modelId}), synthesising…\n`);

const r = textToSpeech({ modelId, text, inputType: "text", stream: false });
const buf = await r.buffer;

await unloadModel({ modelId });

writeFileSync(outPath, toWav(buf, SAMPLE_RATE));
process.stderr.write(`tts_once: written ${buf.length} samples → ${outPath}\n`);
process.exit(0);
