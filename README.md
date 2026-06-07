# Survival Co-pilot

> **QVAC Hackathon I — _Unleash Edge AI_ entry.** Off-grid **survival & rescue** AI for when the network goes down — whether a disaster knocks out telecom or you are simply beyond all cell and internet coverage.

> ⚠️ **DEMO ONLY — DO NOT RELY ON THIS IN A REAL EMERGENCY** ⚠️
> A hackathon demo of a local-AI-over-LoRa architecture. Answers are grounded in a small bundled corpus via RAG, but the model is a 1.7B LLM and the corpus is a seed — replies may still be wrong or incomplete. In a real emergency call 119 / 112 / your local SAR. LoRa replies are prefixed `[demo]`.

People on the ground carry handheld **Meshtastic** LoRa radios. A base station (a laptop today, a solar-powered single-board computer tomorrow) runs a **fully on-device LLM + RAG through the [QVAC SDK](https://qvac.tether.io/)** and auto-answers questions over the mesh. **No internet. No cell signal. No cloud. No central point of failure.**

## Why this fits QVAC

QVAC's thesis is that AI must run *privately, locally, and without permission on any device*. A total signal blackout — from disaster or sheer remoteness — is the literal proving ground: when the network is down, the AI must still work, and lives may depend on it. This project demonstrates QVAC delivering the four things edge AI should beat the cloud on:

- **Private** — every query and answer stays on the device; no cloud ever sees it.
- **Resilient** — works with towers, grid, and internet gone; the mesh has no single point to knock out.
- **Fast** — local inference answers in seconds, with no datacentre round-trip you couldn't reach anyway.
- **Low-cost** — runs on a laptop / Pi; no cloud bills, no per-call fees, no vendor lock-in.

**All inference runs through `@qvac/sdk`** — both the chat LLM and the RAG embeddings. There is no other inference path and no cloud fallback.

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

Two co-operating processes, bridged by a local HTTP API:

- **`qvac serve openai`** (Node, `@qvac/sdk`) — loads the LLM **and** the embedding model, exposes an OpenAI-compatible API on `127.0.0.1:11434`.
- **`bot/basestation.py`** (Python) — owns the BLE radio (`meshtastic-python`), embeds the query + retrieves top-k from the local corpus (RAG), refuses out-of-scope questions, calls the LLM, chunks the reply to ≤200 bytes, sends it back.

Why split: `meshtastic-python`'s BLE is stable on macOS; the QVAC SDK is Node. The local HTTP layer is the clean, cloud-free bridge. Full visual: open `docs/architecture.zh.html` (zh) / `docs/architecture.en.html` (en).

## Requirements (BYOH)

- **Node 22** (see `.nvmrc`) and **Python 3.10+**
- macOS or Linux
- For the full mesh path: a **Meshtastic** device reachable over **BLE** (any model). *Not required* to reproduce the AI core — see the no-hardware path below.

## Setup & run (reproducible)

```bash
git clone <this-repo> QVAC && cd QVAC
npm install                                   # QVAC SDK + CLI
python3 -m venv .venv && source .venv/bin/activate
pip install -r bot/requirements.txt
```

**1. Start the QVAC server** (Terminal A) — loads `co-pilot` (LLM) + `embed-mlm` (embeddings) from `qvac.config.json`:

```bash
npx qvac serve openai            # or: ./node_modules/.bin/qvac serve openai
```

**2. (Re)build the RAG index** — only needed if you edit `knowledge/*.md`; `knowledge/index.json` is committed:

```bash
python bot/build_index.py        # embeds every corpus chunk via @qvac/sdk /v1/embeddings
```

**3a. Reproduce the AI core WITHOUT any radio** (recommended for reviewers):

```bash
python bot/check_embeddings.py            # sanity-check embeddings (prints a 768-dim vector)
python bot/smoketest.py "bitten by a snake — what do I do"   # full RAG + LLM, no BLE
python bot/smoketest.py "what's the bitcoin price"           # off-topic → refused before the LLM
```

**3b. Full mesh path** (Terminal B) — **quit the Meshtastic.app GUI first** (macOS BLE is single-owner):

```bash
cp bot/.env.example bot/.env     # optionally set MESH_BLE_ADDRESS / BASE_LAT / BASE_LON
python bot/basestation.py
```

Then from a handheld Meshtastic device, send `?bitten by a snake — what do I do` (note the `?` prefix). The bot DMs a chunked, grounded reply.

## Configuration (`bot/.env`)

| Var | Default | Effect |
|---|---|---|
| `MESH_BLE_ADDRESS` | empty | Specific node name/MAC; empty = auto-pick first Meshtastic peripheral |
| `QVAC_BASE_URL` | `http://127.0.0.1:11434/v1` | Local QVAC OpenAI-compatible endpoint |
| `QVAC_MODEL` | `co-pilot` | LLM alias in `qvac.config.json` (→ `QWEN3_1_7B_INST_Q4`) |
| `QVAC_EMBED_MODEL` | `embed-mlm` | Embedding alias (→ `EMBEDDINGGEMMA_300M_Q4_0`) |
| `TRIGGER_PREFIX` | `?` | Only answer messages starting with this. Empty = answer everything |
| `REPLY_MODE` | `dm` | `dm` = direct to sender · `channel` = same channel |
| `SEND_INTERVAL_S` | `2.0` | Gap between LoRa segments (duty-cycle friendly) |
| `MAX_REPLY_CHARS` | `1000` | Hard cap before chunking |
| `BASE_LAT` / `BASE_LON` / `BASE_ALT` | empty | Base-station location → enables distance/bearing to senders in the log |

## How RAG keeps answers grounded

- Corpus: `knowledge/{zh,en}/*.md` (bilingual survival topics), split by `##` heading into chunks.
- `bot/index.py` embeds each chunk via `@qvac/sdk` (**EmbeddingGemma 300M Q4**, L2-normalized 768-dim) → `knowledge/index.json`.
- `bot/retriever.py` loads the index and returns cosine top-k for each query. **Cross-lingual**: a Chinese query retrieves relevant English chunks and vice versa.
- **Refuse, don't hallucinate**: if the top score is below `0.40`, the bot replies "out of scope" **before** the LLM runs — no confident wrong answers on life-critical topics.

## Models (aliases in `qvac.config.json`)

| Alias | Model | Role |
|---|---|---|
| `co-pilot` | `QWEN3_1_7B_INST_Q4` | chat / completions (strong zh-TW, ~1 GB RAM) |
| `embed-mlm` | `EMBEDDINGGEMMA_300M_Q4_0` | embeddings for RAG (multilingual, ~150 MB Q4) |

Upgrade path: point `QVAC_MODEL` at a larger GGUF alias (e.g. Qwen2.5-7B) if the base station has ≥16 GB RAM.

## Project layout

```
bot/                  Python base-station bot — the runtime (owns the radio + RAG)
  basestation.py      mesh receive → RAG retrieve → QVAC LLM → chunk → send
  build_index.py      build knowledge/index.json via @qvac/sdk embeddings
  retriever.py        numpy cosine top-k retriever (threshold 0.40 → refuse)
  reply.py            output cleanup (strips empty <think> shells)
  chunker.py          200-byte UTF-8-safe LoRa segmentation
  smoketest.py        full RAG + LLM flow WITHOUT BLE (no-hardware repro)
  check_embeddings.py embeddings sanity check
  injection_test.py   prompt-injection resistance check → evidence/
  system_prompt.txt   system prompt (read at startup)
  .env.example        all runtime knobs
knowledge/{zh,en}/    bilingual RAG corpus  ·  index.json (built artifact)
tools/                Node helpers (run via @qvac/sdk)
  langdetect.mjs      query language detection (QVAC @qvac/langdetect-text)
  audit_run.mjs       auditable inference log (load/unload, TTFT, tokens/sec)
  gen_tts.mjs         deck narration audio via QVAC on-device TTS
docs/                 architecture diagrams + pitch deck + narration
  architecture.md / .zh.html / .en.html   system diagrams
  slides.html         pitch deck (open in a browser, arrow keys to navigate)
qvac.config.json      QVAC model aliases (co-pilot + embed-mlm)
remote-apis.yaml      remote-API disclosure (declares: none at runtime)
```

## Constraints

- **~200 bytes** per LoRa text segment (UTF-8-safe, never split mid-codepoint).
- **No cloud calls anywhere** — all inference is local via `@qvac/sdk`; if a dependency needs the network, it doesn't ship.
- **BLE is single-owner** on macOS — the bot and the Meshtastic GUI can't both hold the radio.

## Roadmap

- **Opportunistic outbound uplink (store-and-forward gateway).** The base station is offline-first, but given *any* outbound link — cellular, satellite, ham/radio, or internet — it would relay an incoming SOS (with the sender's GPS + telemetry from the SAR log) out to responders. Satellite/cellular become *optional* bridges, never requirements; the system always degrades gracefully to fully offline. (This is also why "just use Starlink" misses the point: a single foreign uplink you can be denied is one of our optional bridges, not the foundation.)
- **Solar-powered SBC base station** — move from a laptop to a low-power, solar-capable single-board computer for permanent off-grid deployment.
- **Reliable delivery for long replies** — channel broadcasts have no retransmit, so a long multi-segment answer can drop a segment. Add chunk-level ACK/retry (or reliable unicast) for completeness.

## License

[MIT](./LICENSE) — fully open-source, yours to run, modify, and ship with no vendor lock-in.
