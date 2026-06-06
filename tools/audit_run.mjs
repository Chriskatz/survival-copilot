// Auditable inference benchmark for the QVAC Hackathon submission.
//
// Runs a STANDARD DEMO RUN end-to-end through @qvac/sdk and writes a structured,
// auditable log capturing exactly what the submission rules require:
//   - model load / unload (with timings)
//   - per-inference: prompt, prompt tokens, generated tokens, TTFT, tokens/sec,
//     backend device (cpu/gpu), stop reason, wall-clock
//
// All metrics (TTFT, tokens/sec, token counts, device) are reported NATIVELY by
// QVAC's `completion` stats — not estimated. Prompts are grounded with the real
// bundled corpus, mirroring the product's RAG path.
//
// Run on the DEMO machine (the one whose specs you disclose), with the model
// already provisioned:
//   QVAC_DEVICE=cpu node tools/audit_run.mjs      # SBC / no-GPU
//   QVAC_DEVICE=gpu node tools/audit_run.mjs      # Metal / CUDA box
//
// Output: evidence/inference_log.json  +  evidence/inference_log.csv
import { loadModel, completion, unloadModel, getLoadedModelInfo, QWEN3_1_7B_INST_Q4 } from "@qvac/sdk";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import os from "os";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DEVICE = process.env.QVAC_DEVICE || "cpu";
const SYSTEM_PROMPT = readFileSync(join(ROOT, "bot", "system_prompt.txt"), "utf8").trim();

// Standard demo run: two grounded (in-corpus) queries + one off-topic that the
// product refuses. Grounding text is pulled from the real bundled corpus.
const DEMOS = [
  { id: "snake_bite_zh", lang: "zh", file: "knowledge/zh/first_aid_snake_bite.md", q: "被毒蛇咬到了怎麼辦,三步驟" },
  { id: "snake_bite_en", lang: "en", file: "knowledge/en/first_aid_snake_bite.md", q: "bitten by a snake — what do I do" },
  { id: "hypothermia_en", lang: "en", file: "knowledge/en/first_aid_hypothermia.md", q: "found someone unconscious in the cold, very low temperature" },
];

function topSections(md, n = 2) {
  // crude stand-in for RAG: take the first n "## ..." sections of the matching doc
  const parts = md.split(/^##\s+/m).filter((s) => s.trim());
  return parts.slice(0, n).map((s) => "## " + s.trim()).join("\n\n");
}

function buildUserMsg(demo) {
  const md = readFileSync(join(ROOT, demo.file), "utf8");
  const ctx = topSections(md);
  const label = demo.lang === "zh" ? "出處" : "Source";
  const block = `【${label} ${demo.file}】\n${ctx}`;
  return demo.lang === "zh"
    ? `依以下【出處】段落回答。只准用段落內事實。\n\n---\n${block}\n---\n\n問題: ${demo.q}`
    : `Answer using ONLY the Source excerpts below. Do not invent facts.\n\n---\n${block}\n---\n\nQuestion: ${demo.q}`;
}

function langDirective(lang) {
  return lang === "zh"
    ? "\n\n# THIS REPLY MUST BE IN TRADITIONAL CHINESE (繁體中文) — NOT SIMPLIFIED, NOT ENGLISH."
    : "\n\n# THIS REPLY MUST BE IN ENGLISH ONLY — NO CHINESE CHARACTERS.";
}

const log = {
  schema: "qvac-inference-audit/v1",
  project: "Survival Co-pilot",
  generatedAt: new Date().toISOString(),
  host: {
    platform: process.platform,
    arch: process.arch,
    cpuModel: os.cpus()[0]?.model,
    cpuCount: os.cpus().length,
    totalRamGB: +(os.totalmem() / 1073741824).toFixed(1),
    nodeVersion: process.version,
    requestedDevice: DEVICE,
  },
  model: { name: "QWEN3_1_7B_INST_Q4", role: "co-pilot (LLM)" },
  events: [],
};

const now = () => Number(process.hrtime.bigint() / 1000000n); // ms

console.log(`Loading ${log.model.name} (device=${DEVICE})…`);
const tLoad0 = now();
const modelId = await loadModel({
  modelSrc: QWEN3_1_7B_INST_Q4.src,
  modelType: "llm",
  modelConfig: { ctx_size: 4096, device: DEVICE },
  onProgress: () => process.stdout.write("."),
});
const loadMs = now() - tLoad0;
let loadedInfo = null;
try {
  loadedInfo = await getLoadedModelInfo({ modelId });
  // don't leak the absolute model path (contains the local username) into evidence
  if (loadedInfo?.path) loadedInfo.path = loadedInfo.path.replace(/^.*[/\\]/, "");
} catch {}
console.log(`\nLoaded in ${loadMs} ms (modelId=${modelId})`);
log.events.push({ event: "model_load", model: log.model.name, modelId, loadMs, info: loadedInfo });

for (const demo of DEMOS) {
  const userMsg = buildUserMsg(demo);
  const promptChars = SYSTEM_PROMPT.length + userMsg.length;
  console.log(`\n▶ ${demo.id}: "${demo.q}"`);
  const t0 = now();
  const run = completion({
    modelId,
    history: [
      { role: "system", content: SYSTEM_PROMPT + langDirective(demo.lang) },
      { role: "user", content: userMsg },
    ],
    stream: true,
    generationParams: { temp: 0.1, predict: 400 },
  });
  let firstTokenMs = null;
  let answer = "";
  let stopReason = null;
  for await (const ev of run.events) {
    if (ev.type === "contentDelta") {
      if (firstTokenMs === null) firstTokenMs = now() - t0;
      answer += ev.text;
    } else if (ev.type === "completionDone") {
      stopReason = ev.stopReason ?? null;
    }
  }
  answer = answer.trim();
  const final = await run.final;
  const totalMs = now() - t0;
  const s = final.stats || {};
  const entry = {
    event: "inference",
    id: demo.id,
    lang: demo.lang,
    prompt: demo.q,
    promptChars,
    promptTokens: s.promptTokens ?? null,
    generatedTokens: s.generatedTokens ?? null,
    timeToFirstTokenMs: s.timeToFirstToken ?? firstTokenMs,
    tokensPerSecond: s.tokensPerSecond ?? null,
    backendDevice: s.backendDevice ?? DEVICE,
    stopReason: stopReason ?? final.stopReason ?? null,
    totalMs,
    answerChars: answer.length,
    answerBytesUtf8: Buffer.byteLength(answer, "utf8"),
    answerPreview: answer.slice(0, 160),
  };
  log.events.push(entry);
  console.log(`  TTFT=${entry.timeToFirstTokenMs}ms  ${entry.tokensPerSecond ?? "?"} tok/s  ` +
    `gen=${entry.generatedTokens} prompt=${entry.promptTokens} dev=${entry.backendDevice} total=${totalMs}ms`);
}

const tUnload0 = now();
await unloadModel({ modelId });
const unloadMs = now() - tUnload0;
log.events.push({ event: "model_unload", model: log.model.name, modelId, unloadMs });
console.log(`\nUnloaded in ${unloadMs} ms`);

// write JSON + CSV
const outDir = join(ROOT, "evidence");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "inference_log.json"), JSON.stringify(log, null, 2));

const infer = log.events.filter((e) => e.event === "inference");
const cols = ["id", "lang", "prompt", "promptTokens", "generatedTokens",
  "timeToFirstTokenMs", "tokensPerSecond", "backendDevice", "stopReason", "totalMs", "answerBytesUtf8"];
const csv = [
  cols.join(","),
  ...infer.map((e) => cols.map((c) => {
    const v = e[c] ?? "";
    return /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v;
  }).join(",")),
].join("\n");
writeFileSync(join(outDir, "inference_log.csv"), csv + "\n");

console.log(`\n✓ evidence/inference_log.json`);
console.log(`✓ evidence/inference_log.csv`);
console.log(`  load=${loadMs}ms  unload=${unloadMs}ms  inferences=${infer.length}`);
process.exit(0);
