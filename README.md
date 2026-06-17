
**QVAC Hackathon I — Unleash Edge AI entry.**

People in a disaster zone or remote wilderness carry handheld **Meshtastic** LoRa radios. A base station runs a **fully on-device LLM + RAG via the [QVAC SDK](https://qvac.tether.io/)** and auto-answers survival questions over the mesh — no internet, no cell signal, no cloud.

> ⚠️ **DEMO ONLY.** In a real emergency call 911 / 112 / your local SAR. LoRa replies are prefixed `[demo]`.

## Why this fits QVAC

A total signal blackout is the literal proving ground for QVAC's thesis: AI must run privately and locally on any device. This project delivers:

- **Private** — every query stays on the device; no cloud ever sees it.
- **Resilient** — works with towers, grid, and internet gone.
- **Fast** — local inference answers in seconds, no round-trip possible anyway.
- **Low-cost** — runs on a laptop or Pi; no cloud bills, no vendor lock-in.

All inference runs through `@qvac/sdk` — LLM and embeddings. No other inference path, no cloud fallback.

## Architecture

```
[Handheld Meshtastic] ──LoRa──▶ [mesh relays] ──LoRa──▶ [LoRa / Meshtastic Node]
                                                                  │ BLE
                                                                  ▼
                                  ┌───────────────────────────────────────────┐
                                  │ Base station (laptop / SBC) — 100% local    │
                                  │                                             │
                                  │  basestation.py ──HTTP──▶ qvac serve openai │
                                  │   owns BLE, RAG retrieve,    @qvac/sdk:      │
                                  │   chunk ≤200B                · co-pilot (LLM)│
                                  │                              · embed-mlm     │
                                  └───────────────────────────────────────────┘
```

Two local processes, bridged by HTTP — no cloud anywhere:

- **`qvac serve openai`** (`@qvac/sdk`) — LLM + embedding model on `127.0.0.1:11434`.
- **`bot/basestation.py`** (Python) — owns BLE, retrieves RAG top-k, calls the LLM, chunks the reply to ≤200 bytes, sends back.


## Requirements

- **Node.js 22+** + **Python 3.10+** — macOS or Linux (tested on Node 25.2.1 / Python 3.14.4)
- A **Meshtastic** device over BLE — only needed for the full mesh path; the AI core runs without hardware (see below).

## Setup & run (reproducible)

```bash
git clone https://github.com/Chriskatz/survival-copilot.git QVAC && cd QVAC
npm install                                   # QVAC SDK + CLI
python3 -m venv .venv && source .venv/bin/activate
pip install -r bot/requirements.txt
```

**1. Start QVAC** (Terminal A):
```bash
npx qvac serve openai
```

**2. Rebuild the RAG index** — only if you edit `knowledge/*.md`; `index.json` is already committed:
```bash
python bot/build_index.py
```

**3a. No-hardware path** (recommended for reviewers):
```bash
python bot/smoketest.py "bitten by a snake — what do I do"   # RAG + LLM, no radio
python bot/smoketest.py "what's the bitcoin price"           # off-topic → refused
```

**3b. Full mesh path** (Terminal B) — quit Meshtastic.app first (BLE is single-owner on macOS):
```bash
cp bot/.env.example bot/.env
python bot/basestation.py
```
Send `?your question` from any Meshtastic device; the bot DMs a chunked, grounded reply.

## Configuration (`bot/.env`)

| Var | Default | Effect |
|---|---|---|
| `MESH_SERIAL_PORT` | _(empty)_ | USB serial port (`auto` = auto-detect). **Recommended** for a stationary base station — avoids macOS BLE silent-drop. Leave empty to use BLE instead. |
| `MESH_BLE_ADDRESS` | auto | BLE only (ignored when `MESH_SERIAL_PORT` is set). Node name or MAC; empty = first found. |
| `TRIGGER_PREFIX` | `?` | Messages starting with this are answered; empty = all |
| `REPLY_MODE` | `dm` | `dm` = direct to sender · `channel` = same channel |
| `QVAC_MODEL` | `co-pilot` | LLM alias in `qvac.config.json` |
| `QVAC_EMBED_MODEL` | `embed-mlm` | Embedding alias |

Full list: `bot/.env.example`.

## How RAG keeps answers grounded

- Corpus: `knowledge/{zh,en}/*.md` — bilingual survival topics, chunked by `##` heading.
- Each chunk is embedded via `@qvac/sdk` (EmbeddingGemma 300M Q4, 768-dim) → `knowledge/index.json`.
- At query time: cosine top-k retrieval. **Cross-lingual** — a Chinese query retrieves relevant English chunks and vice versa.
- **Refuse before hallucinate**: if the top score is below `0.40`, the bot replies "out of scope" without calling the LLM.

## Models (aliases in `qvac.config.json`)

| Alias | Model | Role |
|---|---|---|
| `co-pilot` | `QWEN3_1_7B_INST_Q4` | chat / completions (strong zh-TW, ~1 GB RAM) |
| `embed-mlm` | `EMBEDDINGGEMMA_300M_Q4_0` | embeddings for RAG (multilingual, ~150 MB Q4) |

To upgrade: point `QVAC_MODEL` at a larger GGUF alias (e.g. Qwen2.5-7B) if RAM allows.

## Project layout

```
bot/               base-station runtime (BLE · RAG · LLM · chunker · triage · IR · SDR)
knowledge/{zh,en}/ bilingual RAG corpus + index.json
tools/             Node helpers (audit log, TTS, lang-detect)
qvac/              QVAC SDK worker bundle (auto-generated)
evidence/          inference audit log — model load/unload + TTFT/tok/s for one demo run
incidents/         sample Incident Reports from live demo runs (HIGH + CRITICAL)
qvac.config.json   model aliases (co-pilot + embed-mlm)
remote-apis.yaml   remote-API disclosure (none at runtime)
REPRODUCIBILITY.md hardware specs + step-by-step setup for all demo devices
```

## Constraints

- ≤200 bytes per LoRa segment (UTF-8-safe chunking, never mid-codepoint).
- No cloud calls — all inference is local via `@qvac/sdk`.
- BLE is single-owner on macOS — quit the Meshtastic GUI before running the bot.

## Roadmap

| Phase | Status | Feature |
|-------|--------|---------|
| I | ✅ Done | LoRa mesh · RAG · on-device LLM · bilingual reply |
| II | ✅ Done | AI triage · Incident Report (IR) · SDR FM broadcast via PortaPack H4M |
| III | 🔜 Future | Two-way SAR relay — HackRF RX + Whisper STT + LoRa relay back to victim |

**Further:**
- **Opportunistic uplink** — relay SOS over any available link (cellular, satellite) when present; degrades gracefully to fully offline.
- **Solar SBC** — replace the laptop with a low-power SBC for permanent off-grid deployment.
- **Reliable chunked delivery** — chunk-level ACK/retry so long replies survive noisy LoRa channels.

## License

[Apache 2.0](./LICENSE) — fully open-source, yours to run, modify, and ship with no vendor lock-in.
