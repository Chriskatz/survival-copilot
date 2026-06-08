# Survival Co-pilot — Demo / Pitch Narration

Voice-over script for `slides.html`, one block per slide. ~15–20s each, ~3 min total.
Feed each block to a TTS engine (QVAC TTS if available — verify in the QVAC docs/Discord;
otherwise any TTS or record your own voice). English (EN) + Traditional Chinese (ZH).

> Tip: keep delivery calm and clear — it's an emergency-tech product.

---

## 1 · Title
**EN —** When disaster strikes — a quake, a typhoon, or just deep wilderness — the first thing to vanish is the network. Survival Co-pilot is an off-grid AI that still answers life-saving questions when there's no internet, no cell, and no cloud.

**ZH —** 當災害發生 —— 地震、颱風，或身處深山 —— 第一個消失的就是網路。Survival Co-pilot 是一個離線 AI，在沒有網路、沒有訊號、沒有雲端時，依然能回答救命的問題。

---

## 2 · Problem
**EN —** Exactly when someone needs help most, the signal is gone. Cloud AI goes dark the moment the bars hit zero — and the information that could save a life is the information you can't reach.

**ZH —** 偏偏在最需要幫助的時候，訊號沒了。雲端 AI 一旦沒訊號就完全失效 —— 而能救命的資訊，正好是你連不上的那些資訊。

---

## 3 · Solution
**EN —** Our answer: send a short text question over a LoRa mesh, and a local AI replies. People use ordinary Meshtastic radios; a base station runs the AI fully on-device — grounded, and free for everyone.

**ZH —** 我們的解法：用 LoRa mesh 發一則簡短的文字問題，由本機 AI 回答。大家用一般的 Meshtastic 手持機；基地台則完全在本機跑 AI —— 答案有知識庫佐證，而且對所有人免費。

---

## 4 · The big picture
**EN —** Here's the whole system. A survivor's node sends a query; it hops peer-to-peer across the mesh relays to the base station, where a local AI processes it and sends a grounded answer back — with zero infrastructure.

**ZH —** 這是整個系統。求救者的節點送出問題，訊息在 mesh 中繼之間點對點多跳，抵達基地台，由本機 AI 處理後，再把有依據的答案原路送回 —— 全程不需任何基礎建設。

---

## 5 · Live demo
**EN —** And it works on real hardware. A live exchange over LoRa from a phone with no SIM and no Wi-Fi: a hypothermia question answered in seconds, grounded against our knowledge base — and an off-topic question refused, not guessed.

**ZH —** 而且它在真機上跑得起來。這是用一支沒有 SIM、沒有 Wi-Fi 的手機，透過 LoRa 的實際對話：一個失溫問題，幾秒內依知識庫佐證回覆 —— 而離題的問題則被拒答，不亂猜。

---

## 6 · Grounded & safe
**EN —** Because lives are at stake, it refuses rather than guess. Every answer is retrieval-grounded; if nothing relevant is found, it says "out of scope" before the model even runs.

**ZH —** 因為攸關性命，它寧可拒答也不亂編。每個答案都有檢索佐證；若找不到相關內容，它會在模型執行前就回「超出範圍」。

---

## 7 · Why edge AI
**EN —** This is why edge AI wins where the cloud can't follow: private — your data never leaves the device; resilient — no central point to fail; available — a local answer when the cloud is out of reach, depending on nothing external; low-cost — it runs on commodity hardware, from a laptop to a Raspberry Pi, with no cloud bills.

**ZH —** 這就是為什麼 edge AI 能贏在雲端到不了的地方：隱私 —— 資料不離開裝置；韌性 —— 沒有單點故障；可用性 —— 雲端連不到時,本機仍給得出答案,不依賴任何外部服務；低成本 —— 跑在一般硬體上,從筆電到 Raspberry Pi,沒有雲端帳單。

---

## 8 · Built on
**EN —** It's built on the QVAC SDK — decentralized, local AI in a single API. Every bit of inference, the LLM and the RAG embeddings, runs through QVAC, on-device, across platforms. The transport is open-source Meshtastic over LoRa.

**ZH —** 它建構在 QVAC SDK 上 —— 一套 API 提供去中心、本機的 AI。所有推論，包括 LLM 與 RAG 向量，全部走 QVAC、在本機、跨平台執行。傳輸層則是開源的 Meshtastic over LoRa。

---

## 9 · Vision
**EN —** And it grows. Drop a base station anywhere the network is down — every new node extends the safety net. Give one any outbound link — cellular, satellite, or radio — and it relays the SOS and location out to responders: offline-first, online whenever it can. Public-good infrastructure for the places that need it most.

**ZH —** 而且它會成長。哪裡斷網就佈一台基地台，每多一個節點就擴大一分安全網。只要基地台有任一條對外連線 —— 行動網路、衛星、或無線電 —— 就把求救與位置轉送出去給外界:離線優先,有路就上線。這是給最需要的地方的公共財基礎建設。

---

## 10 · Closing
**EN —** Survival Co-pilot: life-critical AI that works anywhere. Private. Local. Unstoppable. Open-source, and powered entirely by QVAC.

**ZH —** Survival Co-pilot：隨處可用的救命 AI。Private、Local、Unstoppable —— 完全開源，並由 QVAC 全程驅動。
