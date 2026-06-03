# Survival Co-pilot

> QVAC Hackathon I — *Unleash Edge AI* entry

> ⚠️ **DEMO ONLY — DO NOT USE IN ACTUAL EMERGENCIES** ⚠️
> This project demonstrates a local-AI-over-LoRa architecture for a hackathon. The bundled Qwen3-1.7B model has **no medical / wilderness expertise** and may produce dangerously wrong instructions. In a real emergency, call 119 / 112 / local SAR. The RAG layer (planned next) will ground answers in verified sources; until then, treat every reply as illustrative of the *pipeline*, not the *advice*.

Off-grid wilderness AI assistant. Hikers carry handheld **Meshtastic** LoRa radios; a base-station MacBook with a **Wio Tracker L1 Pro** over BLE runs a **local LLM via the QVAC SDK** and auto-answers questions over the mesh. No cloud. No cell signal needed. No central point of failure.

## Why this fits QVAC

QVAC's thesis is that AI must run *privately, locally, without permission*. Wilderness is the literal proving ground: when there is no internet, the AI must still work — and lives may depend on it.

## Architecture

```
[Hiker handheld Meshtastic]──LoRa──▶[mesh peers]──LoRa──▶[Wio Tracker L1 Pro]
                                                                  │ BLE
                                                                  ▼
                                                  ┌─────────────────────────┐
                                                  │ MacBook (base station)  │
                                                  │  Python bot.py          │  ←── meshtastic-python BLE
                                                  │       │                 │
                                                  │       ▼ HTTP            │
                                                  │  qvac serve openai      │  ←── @qvac/sdk LLM (Node)
                                                  └─────────────────────────┘
```

Two co-operating processes on the Mac:
- **`qvac serve openai`** — Node, runs the local LLM, exposes an OpenAI-compatible HTTP API on `127.0.0.1:11434`.
- **`bot/bot.py`** — Python, owns the BLE radio, listens on `meshtastic.receive`, asks the LLM, chunks the reply to ≤200 bytes, sends back.

Why split: Meshtastic's BLE stack is native-Python-friendly on macOS; QVAC SDK is Node-only. The OpenAI HTTP layer is the clean bridge.

## Stack

- **Mesh**: [`meshtastic`](https://pypi.org/project/meshtastic/) (Python) over BLE to Wio Tracker L1 Pro
- **AI**: [`@qvac/sdk`](https://docs.qvac.tether.io/) — `QWEN3_1_7B_INST_Q4` (~1 GB RAM, strong zh-TW)
- **Bridge**: QVAC OpenAI-compat HTTP at `http://127.0.0.1:11434/v1`
- **Chunker**: 200-byte UTF-8-safe segmentation (TS + Python copies, same algorithm, both unit-tested)

## Run order

> **Quit the Meshtastic.app GUI first.** macOS BLE is single-owner — if the GUI holds the connection, the bot can't take it.

```bash
# Terminal 1 — LLM server
cd /path/to/QVAC
npm install                    # one-time
npx qvac doctor                # one-time host sanity check
npx qvac serve openai -v       # auto-loads qvac.config.json → alias "co-pilot"

# Terminal 2 — Meshtastic bot
cd /path/to/QVAC
python3 -m venv .venv && source .venv/bin/activate
pip install -r bot/requirements.txt
cp bot/.env.example bot/.env   # edit if you want a specific BLE name/address
python bot/bot.py
```

Then from a handheld Meshtastic device, send `?有人被蛇咬怎麼辦` on the primary channel. The bot replies in chunks.

## Bot behaviour & knobs

Edit `bot/.env`:

| Var | Default | Effect |
|---|---|---|
| `MESH_BLE_ADDRESS` | empty | Specific device name/MAC; empty = auto-pick |
| `QVAC_BASE_URL` | `http://127.0.0.1:11434/v1` | Where the LLM HTTP lives |
| `QVAC_MODEL` | `co-pilot` | Model alias defined in `qvac.config.json` (maps to `QWEN3_1_7B_INST_Q4`) |
| `TRIGGER_PREFIX` | `?` | Only respond to messages starting with this. Empty = answer everything (noisy!) |
| `REPLY_MODE` | `dm` | `dm` = direct to sender, `channel` = reply on same channel |
| `SEND_INTERVAL_S` | `2.0` | Gap between segments, friendly to LoRa duty cycle |
| `MAX_REPLY_CHARS` | `600` | Hard cap before chunking, keeps on-air time sane |

## Project layout

```
src/                          (Node side, mostly future RAG / model loader)
  index.ts                    demo: print system prompt + chunked sample
  mesh/chunker.{ts,test.ts}   200-byte UTF-8-safe segmentation (TS)
  llm/prompts.ts              system prompt
  llm/model.ts                chosen QVAC model constant
bot/                          (Python side, owns the radio)
  bot.py                      mesh receive → QVAC HTTP → chunk → send
  chunker.py                  Python mirror of TS chunker
  chunker_test.py             unittest, mirrors the TS test set
  system_prompt.txt           same prompt, kept readable for fast iteration
  requirements.txt
  .env.example
knowledge/                    offline reference corpus for RAG (todo)
```

## What's done

- ✅ Project scaffold, strict TypeScript, ESM
- ✅ LoRa chunker — TS + Python, both UTF-8 safe, both tested (6/6 passing in Python)
- ✅ System prompt tuned for terse, life-critical, language-mirroring replies
- ✅ Python BLE bot wired end-to-end: subscribe → trigger filter → LLM call → chunked send
- ✅ Self-message filter so the bot doesn't reply to itself

## What's next

1. **First end-to-end test** — quit GUI, start `qvac serve openai`, run bot, send `?test` from a handheld.
2. **RAG layer** — embed `knowledge/*.md` on QVAC side, retrieve top-k per query, prepend to the user message in `ask_llm()`.
3. **Demo script** — pre-baked queries (snake bite, lost, mushroom), record short video for judges.
4. **Optional polish** — rate limit per sender (1 req / 30 s), persistent log of Q/A pairs, simple TUI showing live conversations.

## Model choice

`QWEN3_1_7B_INST_Q4` (1.7B, Q4, ~1 GB RAM). Recorded in `src/llm/model.ts` and `bot/.env`.

Picked because:
- Qwen family has the strongest zh-TW / zh-CN support among small open models — field queries in Chinese must work.
- 1.7B Q4 keeps total round-trip under ~10 s on M-series, leaving budget for LoRa transit.
- Pairs with RAG over `knowledge/` to cover medical / botanical specifics the small model doesn't recall.

Rejected:
- `QWEN3_600M_INST_Q4` — too small, hallucinates on life-critical answers.
- `LLAMA_3_2_1B_INST_Q4_0` — weak Chinese.
- QVAC `MedPsy-1.7B / 4B` — English-only and medical-only; wilderness scope is broader.

Upgrade path: swap `QVAC_MODEL` to a Qwen2.5-7B-Instruct GGUF alias if the demo laptop has ≥16 GB RAM and ~20 s response time is acceptable.

## Demo-safe question bank

Until RAG is wired, the small model hallucinates on medical specifics. For first end-to-end tests + judge demos, use **low-stakes** questions where wrong details don't endanger anyone:

- `?用樹枝怎麼生火`
- `?怎麼用北斗七星找北方`
- `?雙繩結怎麼打`
- `?哪些昆蟲不能碰`
- `?手機沒訊號怎麼求救`
- `?自我介紹一下你是誰`(meta-check the bot is alive)

Avoid until RAG is in:
- Specific medical dosages, snake-bite protocol, mushroom edibility, dehydration thresholds — these need verified sources, not a 1.7B model's guesses.

## Roadmap to trustworthy answers

1. **Now**: local LLM behind LoRa, replies prefixed `[demo]`, README disclaimer ✅
2. **Next**: RAG layer — embed verified survival/first-aid corpus (Wilderness Medical Society PDFs, Red Cross zh-TW, MSF) via `/v1/embeddings`, retrieve top-k per query, pass as context.
3. **Later**: refuse-to-answer guardrail (if RAG retrieves nothing relevant, reply `不在我的知識範圍內,請 SOS`).
4. **Stretch**: structured output for triage (JSON with `severity / action / sos_recommended`).

## Constraints to remember

- **228 bytes** is the safe LoRa text-payload ceiling; we target **200** with an 8-byte header reserve.
- **Never invent** medical dosages, plant edibility, or geographic facts — system prompt enforces this; RAG will reinforce.
- **No cloud calls anywhere.** If a dependency needs network, it doesn't ship.
- **BLE is single-owner** on macOS. Bot vs. GUI app — only one at a time.
