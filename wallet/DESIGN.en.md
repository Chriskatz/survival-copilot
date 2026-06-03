# Donation Design — Survival Co-pilot "Support the Station"

> **Status**: v1 design **finalized** (the 7 decisions in §11 were locked on 2026-06-03), **not yet implemented**. Suggested implementation branch: `wdk-donate`.
> **Purpose**: Q&A is **free and ungated for everyone**. WDK + Tether power a **voluntary donation** layer that supports the base station's ongoing operation (power, maintenance, future solar stations).
> **Out of scope**: modifying the phone app, gating access behind payment, KYC/AML, multi-chain.

---

## 0. Why we pivoted (pay-per-question → donation)

The earlier draft (v0) metered access: prepaid questions, deducted per answer. This version **removes the paywall entirely**, because:

- **Life-critical information must not sit behind a paywall.** Someone lost, hypothermic, or snake-bitten on a mountain should never be unable to get survival steps because a balance ran out. Q&A is always free.
- **The base station is a public good with ongoing cost.** Running one means continuous power, maintenance, and hardware depreciation. Rather than charge the person in distress, let **beneficiaries and supporters donate voluntarily** to keep the station alive.
- **The vision is a self-sustaining off-grid mutual-aid network.** Future base stations can run on solar power, deployed at remote peaks, trailheads, and mountain huts. Donation flow makes "deploy one more station" sustainable — far more in tune with the QVAC "unstoppable / public infrastructure" story than "charge a stranded hiker $0.01."
- **Donation and access are fully decoupled.** Whether or how much you donate has zero effect on anyone's ability to ask questions.

---

## 1. One-liner

Anyone can `?ask` for free. To support the station's long-term operation there are two donation channels: **(A)** sign a **donation authorization** at home (WDK client-side), then send `!donate <string>` once on the mesh — the bot thanks you and settles to TRON USDT when back online; **(B)** the bot advertises the station's **TRON address + QR** via `!support`, so anyone can donate directly with their own wallet.

---

## 2. The two donation channels

| | Channel A — on-mesh `!donate` (signed) | Channel B — advertised address / QR |
|---|---|---|
| Best for | Expressing support in the moment; showcasing WDK | Donors who prefer their own wallet, their own time |
| User action | Sign at home, paste one string on mesh | See the address/QR, transfer when online |
| On-chain timing | Bot batch-settles on return | Donor transfers directly |
| WDK-bound? | Yes (client-side signing) | No (any TRON wallet works) |
| Trust model | Bot proxies settlement (testnet for demo) | Peer-to-peer, never touches the bot |

Both are kept, so "the technically inclined showcase WDK" and "users donate their own way" both hold.

---

## 3. User flows

### Channel A (on-mesh signed authorization)
```
Valley (4G/wifi)               Mountain (off-grid)           Back online
─────────────────              ───────────────────           ────────────
 1 Open donation page (WDK)
 2 Enter/generate WDK seed
 3 Pick amount (free / tiers)
 4 Sign "donation auth"
 5 Copy string / QR
                              6 (free Q&A, no prerequisite)
                                ?how do I get unlost -> bot answers
                              7 (when you want to support, any line)
                                !donate v1.<payload>.<sig>
                              8 bot: "Thank you! Logged $5,
                                will settle on return. You keep
                                this station alive."
                                                              9  base station reconnects
                                                              10 settle.py batch-settles to TRON USDT
                                                              11 on-chain confirmation -> drop from pending
```

### Channel B (advertised address, direct donation)
```
Mountain                                Any time (online)
────────                                ─────────────────
 User asks:  !support  ───────────▶  bot replies station TRON address + one-line note
 (or sees the QR on README / a sticker)  donor transfers USDT with their own wallet
                                         (never touches the bot / mesh)
```

---

## 4. On-mesh donation authorization format (Channel A)

### 4.1 Overview
```
!donate v1.<base58 payload>.<base58 sig>
```
- `!donate` — trigger word; the bot routes on this prefix (fully independent of free `?` Q&A)
- `v1` — schema version
- `payload` — structured fields (below)
- `sig` — Ed25519 signature over the payload (proves the donor authorized it)

### 4.2 Payload fields (binary, fixed length)

| Field | Type | bytes | Notes |
|---|---|---|---|
| donor_pubkey | Ed25519 public | 32 | Donor's WDK-derived identity (for thanks / supporter list) |
| donation_id | random | 8 | Prevents double-settlement (bot remembers settled ids) |
| amount_cents | uint16 BE | 2 | Donation amount (USDT cents, $0.01–$655.35) |
| station_id | bytes | 4 | Target station short ID (first 4 bytes of station pubkey) |
| issued_at | uint32 BE | 4 | Issue time, unix epoch |
| valid_until | uint32 BE | 4 | Authorization expiry (default 30 days) |
| **payload total** | | **54 bytes** | |
| signature (Ed25519 over the 54 bytes) | | 64 | |
| **binary total** | | **118 bytes** | |

After base58 encoding ~161 chars + the `!donate v1..` prefix ≈ **172 chars** — **comfortably within the 200-byte budget**.

> `station_id` is for the **future multi-station network** (the solar mountain-station vision): one authorization only settles to its named station and can't be replayed against another bot. In the single-station demo it's fixed to this station's ID.

### 4.3 Example (fake data)
```
!donate v1.3JqHJfwQzN1xMr9PRkM4dPfX...wLp.5KBJ8vWxYz...Nf2
```

---

## 5. Signatures & identity

### 5.1 Scheme
- **Ed25519**: 64-byte sig, fast verify (<1ms on the bot), deterministic, no nonce footguns.

### 5.2 Key derivation
- Donor's WDK seed derives an Ed25519 key — the seed **never leaves the browser**.
- The bot only sees `donor_pubkey`; it **never has, and never needs, the donor's private key**.

### 5.3 Why Ed25519, not secp256k1
- Ed25519 sig is 64 bytes vs secp256k1 DER 71–72 bytes — saves ~7 bytes (LoRa is precious).
- Faster verify.
- When settling on TRON, the bot signs the USDT tx with its own key (unrelated to the authorization stage).

---

## 6. Bot message handling (Q&A always free)

```
incoming text:
├── starts with "?"        → free Q&A, unchanged, NO balance/identity check
│       └── RAG + LLM -> chunked reply (current behavior)
│
├── starts with "!donate " → wallet/donate.py:handle_donate()
│       ├── parse v1.payload.sig
│       ├── verify Ed25519 sig
│       ├── reject if donation_id already settled (no double-count)
│       ├── reject if valid_until < now (expired authorization)
│       ├── reject if station_id != this station
│       ├── record into pending_donations
│       └── reply "Thank you for your support! Logged $X.XX, settling on return."
│
├── starts with "!support" → station TRON address (plain text) + lifetime total + a pointer to the QR (Channel B)
│       e.g. "This station runs on donations - community has given $123.45 so far.
│            TRON: T...  Scan the QR on the station or open donate.html. Thanks!"
│       note: a QR can't travel over mesh (plain text / wraps / unscannable) -> always off-mesh, see §8.3
│
└── otherwise               → ignore (stays polite on shared mesh)
```

**Key point**: the `?` Q&A path has **no wallet check whatsoever** — no session, no balance, no "out of credit." Donation is a parallel, optional act of support.

---

## 7. Bot state (vastly simpler than v0)

No sessions, no metering, no refunds. Just "donations pending settlement" and "ids already settled."

### 7.1 Persistent (`wallet/donations.json`, atomic write)
```json
{
  "settled_donation_ids": ["base58...", "..."],
  "pending_donations": [
    {
      "donor_pubkey": "base58...",
      "donation_id": "base58...",
      "amount_cents": 500,
      "issued_at": 1717000000,
      "received_at": 1717003600
    }
  ],
  "lifetime_supported_cents": 12345,
  "recent_supporters": [
    { "donor": "3JqH...wLp", "amount_cents": 500, "at": 1717003600 }
  ]
}
```
- On `!donate`, atomic write (`.tmp` then rename).
- `lifetime_supported_cents`: shown by `!support` / demo / README as "community has supported this station with $X."
- `recent_supporters`: the last N supporters' **abbreviated pubkey + amount**, a thank-you shown on README / the demo screen. **Never affects anyone's access.** Abbreviated (not full pubkey) to reduce the identifiability of a semi-public donation record.

---

## 8. Donation page (`wallet/donate.html`)

### 8.1 Spec
- Single HTML file, **works offline** (JS inlined, opens via `file://`) — same spirit as `architecture.html`: zero external dependencies.
- Loads `@tetherto/wdk` + EVM/TRON wallet modules (local bundle).
- UI:
  1. Mnemonic input / generate new seed
  2. **Amount**: free input, plus suggested tier buttons (coffee $1 / battery $5 / sun $20 "fund a solar station for a day")
  3. Target station_id (defaults to this station, carried by QR)
  4. Expiry days (default 30)
  5. "Generate donation authorization" → outputs the `!donate` string + QR
- Also shows Channel B: the station's TRON address + QR for anyone who'd rather not use WDK.

### 8.2 Security
- Seed phrase **never sent to any server** (pure static page).
- Warn: the seed isn't stored after leaving the page; use a **dedicated low-value seed**, not a main wallet.

### 8.3 QR delivery (off-mesh, important)

Meshtastic text messages are plain text, ≤200B/segment, **no images**; the phone chat also wraps lines and uses a proportional font, so a "text QR" (Unicode block chars) gets mangled, is unscannable, and blows the byte budget — **the QR never travels over mesh**. And Channel B donations need internet to settle on-chain anyway, so the donor is online exactly when they'd scan — the QR doesn't need the mesh at all. The QR is generated where there's a screen or a physical surface:

- **Printed QR (most off-grid, recommended)**: a weatherproof sticker on the base station / trailhead sign — scannable on the spot, zero power.
- **`donate.html` client-side (recommended)**: the donor opens the page when back online; it draws the QR from the address (Channel A's donation-authorization QR is also produced on this page).
- **README / project page**: for online visitors.
- `!support` over mesh only returns the **plain-text address + a one-line pointer** to those QRs (see §6).

> If the station wants to "show a QR" to someone standing next to it, pop a QR window on the **Mac screen** or attach an OLED/e-ink — but a 128×64 OLED only fits a short-URL QR; a 34-char address is too dense. That's for people at the station, not the hiker out on the mesh.

---

## 9. Settlement (Channel A, when back online)

### 9.1 Trigger
- Bot detects connectivity → runs `wallet/settle.py`; or manually `python wallet/settle.py --dry-run`.

### 9.2 Flow
```
for d in pending_donations (station == this station):
    bot's TRON wallet executes / broadcasts the corresponding USDT transfer
    on-chain confirmation -> move to settled_donation_ids
```

### 9.3 Demo simplification
- **Demo uses TRON testnet (Nile)**: real sign, real broadcast, real confirmation — but test coins. Beats a mock, and testnet is free.
- Donation is a **one-way gift**: no refunds, no escrow balance, no reconciliation disputes (see §10).

> **Honest trust note**: LoRa can't broadcast an on-chain tx on the mountain, so Channel A's "authorize → settle" has a bot-proxied step in the middle. A truly trustless version (donor pre-funds escrow, or the bot holds a donor-presigned tx that is still valid) is bounded by TRON tx expiry, so it's deferred to v2. For the demo: the authorization is the donor's commitment, and the bot completes it on testnet. Channel B (direct) is trustless by nature and never touches the bot.

---

## 10. Security considerations (donation model, simpler than v0)

### 10.1 Defended
| Attack | Mitigation |
|---|---|
| Re-settling the same authorization | `settled_donation_ids` set + `donation_id` |
| Forging a donation authorization | Ed25519 sig; bot verifies `donor_pubkey` against sig |
| Expired authorization | `valid_until` enforced |
| Cross-station mis-settlement (future multi-station) | `station_id` binding |

### 10.2 No longer problems (because the paywall is gone)
- **No balance to steal** → node-ID spoofing can no longer "spend someone's balance" (there is no balance).
- **No double-open session issue** → there are no sessions.
- **No incentive to under-report spend** → donation is a one-way gift; the bot has no one to over-charge.

### 10.3 Donation-specific considerations
| Item | Handling |
|---|---|
| Bot advertising a wrong/tampered address (Channel B) | Address hard-coded in bot config + README + station sticker, cross-verifiable in multiple places; signed advertisement (optional v2) |
| Flood of fake `!donate` | ~1ms verify each; **LoRa airtime is a natural rate limiter**, not a concern |
| Donor resends the same authorization (network retransmit) | `donation_id` dedupe, settled once |

---

## 11. Finalized decisions (v1, locked 2026-06-03)

1. **Suggested amount tiers**: coffee $1 / battery $5 / sun $20 ("fund a solar station for a day"), plus free input. ✅
2. **`!support` reply**: station TRON address + lifetime support total + one-line note (see §6). ✅
3. **Supporter acknowledgment**: a "recent supporters" list (**abbreviated** donor_pubkey + amount), shown on README / demo — purely thanks, **never affects access** (see §7 `recent_supporters`). ✅
4. **station_id**: include it now (4 bytes, reserves the format for the future multi-station network). ✅
5. **Authorization expiry**: default 30 days, adjustable 7–90. ✅
6. **Demo settlement**: TRON testnet (Nile), **real** sign/broadcast/confirm (free test coins). On-site needs: connectivity + test coins + a configured station wallet on demo day. ✅
7. **Channel B chain**: demo ships one TRON address only for simplicity; multi-chain (BTC / Ethereum) deferred to v2. ✅

---

## 12. Effort estimate (after design approval)

Less than v0 (no sessions/metering/refunds):

| Task | Effort |
|---|---|
| `wallet/donation_format.py` — encode/decode/sign/verify | 0.5 d |
| `wallet/donate.html` — donation page + QR + direct address | 0.5 d |
| `bot/donate.py` — `!donate` / `!support` handling + persistence | 0.5 d |
| `bot/bot.py` changes — route `!donate` / `!support` (`?` untouched) | 0.25 d |
| `wallet/settle.py` — TRON USDT testnet settlement | 0.5 d |
| End-to-end demo + README update (disclaimer + donation notes) | 0.5 d |
| **Total** | **~2.75 d** |

---

## 13. Explicitly not doing

- **Never gate access behind donation** — free Q&A is the core of this design.
- No refunds / escrow balance / reconciliation (donation is a one-way gift).
- No multi-bot settlement sync (single station for now; `station_id` already reserves the format for the future).
- No KYC / AML (hackathon demo).
- No real escrow smart contract (testnet + simple transfer).
- No multi-chain (TRON only; BTC / Ethereum in v2).

---

## 14. Related Memory / Files

- Existing mesh + LLM + RAG documented in [[project-survival-copilot]]
- Existing setup gotchas in [[qvac-setup-gotchas]]
- Architecture overview: `architecture.html` / `architecture.en.html` / `architecture.md`
- After approval, suggested implementation branch: `wdk-donate`
