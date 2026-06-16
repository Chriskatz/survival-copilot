# Reproducibility Instructions — Survival Co-pilot

QVAC Hackathon I · General Purpose track

---

## Hardware

### Base Station (all inference runs here)

| Component | Spec |
|-----------|------|
| Machine | MacBook Pro 16″ (Mac15,7) |
| SoC | Apple M3 Pro |
| CPU | 12-core (6 Performance + 6 Efficiency) |
| GPU | 18-core Apple GPU (unified, Metal) |
| RAM | 36 GB unified memory |
| Storage | 494 GB SSD |
| OS | macOS 26.5 (Build 25F71) |

All QVAC SDK inference runs on the **GPU backend** (`"device": "gpu"` in `qvac.config.json`). No discrete GPU is required — Apple Silicon unified memory is sufficient.

### LoRa Mesh Nodes (×2)

| Component | Spec |
|-----------|------|
| Device | Seeed Wio Tracker L1 Pro |
| Firmware | Meshtastic 2.x |
| Node 1 (victim) | Sends SOS message over LoRa mesh |
| Node 2 (base) | Connected to MacBook via USB serial, relays mesh traffic |

### SDR (Phase II — FM broadcast)

| Component | Spec |
|-----------|------|
| Device | PortaPack H4M (operated in HackRF One mode) |
| Frequency | 469.660 MHz |
| TX gain | 20 dB VGA (configurable via `SDR_TX_GAIN`) |
| TX amp | Off (`SDR_TX_AMP=0`) |
| Interface | USB |

### FM Radio Receiver

| Component | Spec |
|-----------|------|
| Type | Handheld FM radio (×2 available, ×1 used in demo) |
| Role | Receives FM broadcast from SDR to verify audio output |

---

## Software Versions

| Package | Version |
|---------|---------|
| Node.js | v25.2.1 |
| Python | 3.14.4 |
| @qvac/sdk | 0.12.0 |
| @qvac/cli | 0.5.0 |
| meshtastic (Python) | 2.7.8 |
| hackrf_transfer | system-installed via Homebrew (PortaPack H4M, HackRF One mode) |

---

## Models

| Alias | Model ID | Role | Approx. Size |
|-------|----------|------|-------------|
| `co-pilot` | `QWEN3_1_7B_INST_Q4` | LLM — triage + survival Q&A | ~1 GB |
| `embed-mlm` | `EMBEDDINGGEMMA_300M_Q4_0` | RAG embeddings (multilingual) | ~150 MB |
| `tts` | `TTS_EN_SUPERTONIC_Q8_0` | FM broadcast narration (Phase II) | ~200 MB |

Models are downloaded automatically by `@qvac/sdk` on first run via the QVAC decentralized registry (Holepunch/P2P). No user data is sent during this step.

---

## Setup

```bash
git clone https://github.com/Chriskatz/survival-copilot.git QVAC
cd QVAC
npm install                                      # installs @qvac/sdk + @qvac/cli
python3 -m venv .venv && source .venv/bin/activate
pip install -r bot/requirements.txt
cp bot/.env.example bot/.env
```

Edit `bot/.env` as needed (see `bot/.env.example` for all options).

---

## Running the Demo

### Path A — No hardware (AI core only)

No Meshtastic device or HackRF required.

**Terminal A:**
```bash
npx qvac serve openai
```
Wait for `Models loaded` (model load takes ~2.7 s on M3 Pro).

**Terminal B:**
```bash
source .venv/bin/activate
python bot/smoketest.py "bitten by a snake — what do I do"
python bot/smoketest.py "what is bitcoin"         # off-topic → refused
```

Expected output: grounded survival answer in ~1.3 s, off-topic query refused with no LLM call.

### Path B — Full mesh (Phase I)

Requires: Meshtastic device connected via USB serial.

```bash
# In bot/.env:
MESH_SERIAL_PORT=/dev/cu.usbserial-XXXX          # replace with your port
REPLY_MODE=channel

source .venv/bin/activate
python bot/basestation.py
```

Send `?<your question>` from any Meshtastic device. The bot replies to the same channel.

### Path C — Phase II (AI triage + Incident Report + SDR FM)

Requires: Meshtastic device + PortaPack H4M (HackRF One mode) connected via USB.

```bash
# Additional env vars in bot/.env:
SDR_BROADCAST_ENABLED=true
SDR_FREQUENCY_HZ=469660000

source .venv/bin/activate
python bot/basestation.py
```

On CRITICAL or HIGH triage: the bot generates a JSON + Markdown Incident Report in `incidents/`, then broadcasts a spoken FM alert via PortaPack H4M (HackRF One mode) on 469.660 MHz. Any FM radio tuned to that frequency receives the alert.

---

## Observed Performance (M3 Pro, GPU backend)

From `evidence/inference_log.json` (full audit log with model load/unload events):

| Metric | Value |
|--------|-------|
| Model load time | 2,732 ms |
| Time to first token (avg) | ~354 ms |
| Throughput (avg) | ~95 tok/s |
| Model unload time | 31 ms |
| Backend | GPU (Apple Silicon unified) |

Per-query breakdown:

| Query | Lang | TTFT | Tok/s | Total |
|-------|------|------|-------|-------|
| Snake bite (3 steps) | zh | 369 ms | 95.6 | 1,215 ms |
| Snake bite | en | 326 ms | 98.0 | 1,312 ms |
| Hypothermia | en | 366 ms | 92.8 | 1,310 ms |

---

## Evidence Bundle

| File | Description |
|------|-------------|
| `evidence/inference_log.json` | Structured audit log: model_load → inference × 3 → model_unload, with full perf metrics |
| `evidence/inference_log.csv` | Same data in CSV form |
| `evidence/rescue_log.jsonl` | Full mesh demo run: real LoRa packets received from Seeed Wio Tracker L1 |
| `evidence/injection_test.json` | Prompt injection resilience tests (off-topic refusal verification) |
| `remote-apis.yaml` | Structured declaration that zero remote API calls occur at runtime |
| `qvac.config.json` | QVAC SDK model configuration (GPU, ctx_size, preload) |


---

## Minimum Reproducible Hardware

The AI core (LLM + RAG) runs on any Apple Silicon Mac or Linux x86_64 machine with at least **8 GB RAM**. The full Phase II pipeline additionally requires:

- A Meshtastic-compatible LoRa radio (any supported hw_model)
- A PortaPack H4M (HackRF One mode) or any SDR supporting `hackrf_transfer`
