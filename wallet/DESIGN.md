# 捐贈設計草案 — Survival Co-pilot「支持站點」(Support the Station)

> **狀態**: v1 設計**已定案**(§11 七項決策 2026-06-03 拍板),**尚未實作**。實作分支建議 `wdk-donate`。
> **目的**: 問答對所有人**免費且不設門檻**;WDK + Tether 用來做**自願捐贈**,支持基地台的長期運作(電費、維修、未來太陽能站點)。
> **不在範圍內**: 改造手機 app、把捐贈當成付費門檻、KYC/AML、多鏈。

---

## 0. 設計轉向(為什麼從 pay-per-question 改成 donation)

先前的草案(v0)是「預付題數、按題扣款」。本版**整個拿掉計費門檻**,原因:

- **生命攸關的資訊不該被付費牆擋住。** 山上迷路、失溫、被蛇咬的人,不該因為餘額用完而問不到求生步驟。問答永遠免費。
- **基地台是公共財,有長期成本。** 架一台 base station 要持續電費、維修、硬體折舊。與其向求救者收費,不如讓**受惠者與認同這件事的人自願捐贈**來養站。
- **願景是自我永續的離線互助網。** 未來 base station 可改太陽能供電,部署在偏遠高山、登山口、山屋。捐贈金流讓「多放一台站」這件事可持續 —— 這比「向遇難者收 $0.01」更符合 QVAC「unstoppable / 公共基礎建設」的敘事。
- **捐贈與存取完全解耦。** 捐不捐、捐多少,都不影響任何人能不能問問題、問幾題。

---

## 1. 一句話總結

任何人都能免費 `?問問題`;若想支持站點長期運作,有兩條捐贈管道:(A) 山下用網頁(WDK client-side)簽一張**捐贈授權**,進山後 `!donate <字串>` 一次,bot 道謝、回網時結算到 TRON USDT;(B) bot 公告站點的 **TRON 收款地址 + QR**,任何人用自己的錢包直接捐。

---

## 2. 兩條捐贈管道

| | 管道 A — On-mesh `!donate` 簽章 | 管道 B — 公告地址 / QR 直捐 |
|---|---|---|
| 適合 | 想在山上當下就表達支持的人、展示 WDK | 想用自己慣用錢包、自己時間捐的人 |
| 使用者動作 | 山下簽一張授權,山上貼一次字串 | 看到地址/QR,回網時自己轉帳 |
| 鏈上動作時機 | bot 回網後批次 settle | 捐贈者自己當下轉 |
| 綁 WDK? | 是(client-side 簽章) | 否(任何 TRON 錢包都行) |
| 信任模型 | bot 代為結算(demo 用 testnet) | 點對點,不經 bot |

兩條都保留,讓「懂技術的展示 WDK」與「用戶用自己的方式捐」都成立。

---

## 3. 使用者流程

### 管道 A(on-mesh 簽章授權)
```
山下(有 4G/wifi)              山上(off-grid)               下山(回網)
─────────────────              ──────────────                ──────────
 ① 開捐贈網頁(WDK)
 ② 輸入/產生 WDK seed
 ③ 選金額(任意 or 建議級距)
 ④ client-side 簽「捐贈授權」
 ⑤ 複製字串 / QR
                              ⑥（先免費問答,不需任何前置）
                                 ?我迷路了怎麼辦 → bot 直接答
                              ⑦（想支持時,任一句）
                                 !donate v1.<payload>.<sig>
                              ⑧ bot 回 "🙏 感謝支持!已記錄 $5,
                                 下山結算。站點靠你續命。"
                                                              ⑨ base station 回網
                                                              ⑩ settle.py 批次結算到 TRON USDT
                                                              ⑪ 上鏈確認 → 從 pending 移除
```

### 管道 B(公告地址直捐)
```
山上                                    任意時間(有網路)
──────                                  ────────────────
 使用者問:!support  ────────────▶  bot 回站點 TRON 地址 + 一行說明
 （或從 README / 站點貼紙看到 QR）        捐贈者用自己的錢包轉 USDT
                                        （完全不經過 bot / mesh）
```

---

## 4. On-mesh 捐贈授權格式(管道 A)

### 4.1 概觀
```
!donate v1.<base58 payload>.<base58 sig>
```
- `!donate` — 觸發詞,bot 用這個 prefix 分流(與免費 `?` 問答完全獨立)
- `v1` — schema version
- `payload` — 結構化欄位(下節)
- `sig` — 對 payload 的 Ed25519 簽章(證明是捐贈者本人的授權)

### 4.2 Payload 欄位(binary,固定長度)

| 欄位 | 型別 | bytes | 說明 |
|---|---|---|---|
| donor_pubkey | Ed25519 public | 32 | 捐贈者 WDK 衍生身分(用於道謝/支持者名單) |
| donation_id | random | 8 | 防重複結算(bot 記得結過的 id) |
| amount_cents | uint16 BE | 2 | 捐贈金額(USDT 分,$0.01–$655.35) |
| station_id | bytes | 4 | 目標站點短 ID(站點 pubkey 前 4 bytes) |
| issued_at | uint32 BE | 4 | 簽發時間 unix epoch |
| valid_until | uint32 BE | 4 | 授權過期(建議 30 天) |
| **總計 payload** | | **54 bytes** | |
| signature(Ed25519 對上述 54 bytes) | | 64 | |
| **總計 binary** | | **118 bytes** | |

base58 編碼後 ~161 字元 + `!donate v1..` 前綴 ≈ **172 字元**,**安全進 200 byte 預算**。

> `station_id` 是為了**未來的多站點網路**(太陽能高山站點群):同一張授權只結算給指定站點,不會被別台 bot 重複拿去結。單站 demo 階段固定填本站 ID。

### 4.3 範例(假資料)
```
!donate v1.3JqHJfwQzN1xMr9PRkM4dPfX...wLp.5KBJ8vWxYz...Nf2
```

---

## 5. 簽章與身分

### 5.1 簽章方案
- **Ed25519**: 64-byte sig,verify 快(bot 端 <1ms),確定性,無 nonce 漏洞。

### 5.2 Key 衍生
- 捐贈者 WDK seed 衍生(Ed25519 path)— seed **不離開瀏覽器**。
- bot 端只看 `donor_pubkey`,**沒有也不需要捐贈者私鑰**。

### 5.3 為什麼 Ed25519 而非 secp256k1
- Ed25519 sig 64 bytes vs secp256k1 DER 71–72 bytes,省 ~7 bytes(LoRa 寸土寸金)。
- verify 更快。
- 結算到 TRON 時,bot 端用自己的 key 簽 USDT tx(與捐贈授權階段無關)。

---

## 6. Bot 訊息處理(問答永遠免費)

```
incoming text:
├── starts with "?"        → 免費問答流程,完全不變、不檢查任何餘額/身分
│       └── RAG + LLM → chunked reply（現狀）
│
├── starts with "!donate " → wallet/donate.py:handle_donate()
│       ├── parse v1.payload.sig
│       ├── verify Ed25519 sig
│       ├── reject if donation_id 已結算過（防重複）
│       ├── reject if valid_until < now（過期授權）
│       ├── reject if station_id != 本站
│       ├── 記入 pending_donations（待結算）
│       └── reply "🙏 感謝支持！已記錄 $X.XX，下山結算。"
│
├── starts with "!support" → 回站點 TRON 地址（純文字）+ 累計支持額 + 指向 QR（管道 B）
│       例: "本站靠捐贈供電，已獲社群支持 $123.45。
│            TRON: T... 掃基地台上的 QR 或開 donate.html。🙏"
│       註: QR 無法走 mesh（純文字 / 會換行 / 掃不出）→ 一律 off-mesh，見 §8.3
│
└── 其他                    → 忽略（維持 polite-on-shared-mesh）
```

**關鍵**: `?` 問答路徑**完全沒有任何錢包檢查**。沒有 session、沒有餘額、沒有「用完請儲值」。捐贈純粹是平行的、可選的支持行為。

---

## 7. Bot 端狀態(比 v0 大幅簡化)

沒有 session、沒有計題、沒有退款。只需要記「待結算的捐贈」與「結過的 id」。

### 7.1 Persistent(`wallet/donations.json`,atomic 寫檔)
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
    { "donor": "3JqH…wLp", "amount_cents": 500, "at": 1717003600 }
  ]
}
```
- 收到 `!donate` 後 atomic 寫入(`.tmp` 寫完 rename)。
- `lifetime_supported_cents`:給 `!support` / demo / README 顯示「本站累計獲得社群支持 $X」。
- `recent_supporters`:最近 N 位支持者的**縮寫 pubkey + 金額**,純致謝顯示在 README / demo 畫面。**絕不影響任何人的存取**。保留縮寫(非完整 pubkey)以降低公開捐贈紀錄的可識別度。

---

## 8. 捐贈網頁(`wallet/donate.html`)

### 8.1 規格
- 單一 HTML 檔,**離線可用**(JS 內嵌,`file://` 可開)—— 與 `architecture.html` 同精神:零外部相依。
- 載 `@tetherto/wdk` + EVM/TRON wallet 模組(本地 bundle)。
- UI:
  1. Mnemonic 輸入 / 產新 seed
  2. **金額**:自由輸入,另附建議級距按鈕(☕ $1 / 🔋 $5 / ☀️ $20「養一天太陽能站」)
  3. 目標 station_id(預設本站,QR 帶入)
  4. 過期天數(預設 30)
  5. 「產生捐贈授權」→ 輸出 `!donate` 字串 + QR
- 另顯示管道 B:站點 TRON 地址 + QR,讓不想用 WDK 的人直接捐。

### 8.2 安全
- Seed phrase **不送任何 server**(純 static page)。
- 提示:離開頁面後 seed 不保存;建議用**專用小額 seed**,別用主錢包。

### 8.3 QR 交付(off-mesh,重要)

Meshtastic 文字訊息是純文字、≤200B/段、**無圖片**;手機聊天又會換行 + 比例字體,所以「文字 QR」(Unicode 方塊字)會被打亂、掃不出來,且體積爆掉 byte 預算 —— **QR 一律不走 mesh**。而且管道 B 捐款本來就需要網路上鏈,捐贈者掃碼當下必為 online,QR 根本不需經 mesh。QR 在有螢幕/實體的地方生成:

- **實體印刷 QR(最 off-grid,推薦)**: 防水貼紙貼在基地台 / 登山口告示牌,山上當下、零電力可掃。
- **`donate.html` client-side 生成(推薦)**: 捐贈者回網開網頁,由地址即時畫 QR(管道 A 的捐贈授權 QR 也在此頁產生)。
- **README / 專案頁**: 給線上訪客。
- mesh 上的 `!support` 只回**純文字地址 + 一句指向上述 QR**(見 §6)。

> 若基地台想現場「亮一張 QR」給站旁的人,可在 **Mac 螢幕**彈 QR 視窗,或接 OLED/e-ink —— 但 128×64 OLED 只塞得下短網址 QR,34 字地址會太密。這是給站旁的人,不是遠端 mesh 上的登山者。

---

## 9. Settlement(管道 A,山下回網時)

### 9.1 Trigger
- Bot 偵測到網路 → 跑 `wallet/settle.py`;或手動 `python wallet/settle.py --dry-run`。

### 9.2 流程
```
for d in pending_donations (station == 本站):
    bot 用站點 TRON 錢包執行 / 廣播對應的 USDT 轉入
    收到鏈上 confirmation → 移到 settled_donation_ids
```

### 9.3 Demo 簡化
- **Demo 用 TRON testnet(Nile)**:真實簽章、真實 broadcast、真實確認,但用測試幣 —— 比 mock 帥,且 testnet 免費。
- 捐贈是**單向贈與**:沒有退款、沒有 escrow 餘額、沒有對帳爭議(見 §10)。

> **誠實註記(信任邊界)**: LoRa 無法在山上直接廣播鏈上交易,所以管道 A 的「授權→結算」中間有一段 bot 代理。真正 trustless 的做法(捐贈者預存 escrow、或 bot 持有捐贈者預簽且仍有效的 tx)受 TRON tx 過期時間限制,留 v2。Demo 階段:授權即捐贈者的承諾,bot 在 testnet 上代為完成。管道 B(直捐)則天生 trustless,不經 bot。

---

## 10. 安全考量(捐贈模型,比 v0 單純)

### 10.1 已防護
| 攻擊 | 對策 |
|---|---|
| 重複結算同一張授權 | `settled_donation_ids` 集合 + `donation_id` |
| 偽造捐贈授權 | Ed25519 簽章,bot 驗 `donor_pubkey` 配 sig |
| 過期授權 | `valid_until` 強制檢查 |
| 跨站誤結算(未來多站) | `station_id` 綁定 |

### 10.2 不再是問題(因為拿掉了計費門檻)
- **沒有餘額可被盜用** → node ID 偽造不再能「花掉別人的餘額」(根本沒有餘額)。
- **沒有 session 雙開問題** → 沒有 session。
- **沒有「少報花費」誘因** → 捐贈是單向贈與,bot 沒有向使用者多收的對象。

### 10.3 捐贈模型特有的考量
| 項目 | 處理 |
|---|---|
| bot 公告**錯誤/被竄改的收款地址**(管道 B) | 地址寫死在 bot 設定 + README + 站點貼紙,多處可交叉驗證;簽章公告(可選 v2) |
| 惡意大量假 `!donate` | 每張 verify ~1ms;**LoRa airtime 是天然 rate limiter**,不擔心 |
| 捐贈者重複送同一張(網路重傳) | `donation_id` 去重,結算一次 |

---

## 11. 已定案決策(v1,2026-06-03 拍板)

1. **建議金額級距**: ☕$1 / 🔋$5 / ☀️$20(「養一天太陽能站」),另允許自由輸入。✅
2. **`!support` 回應**: 站點 TRON 地址 + 累計支持額 + 一句維運說明(見 §6)。✅
3. **支持者致謝**: 做「最近支持者」名單(donor_pubkey **縮寫** + 金額),顯示於 README / demo,純致謝、**絕不影響存取**(見 §7 `recent_supporters`)。✅
4. **station_id**: 現在就放(4 bytes,為未來多站網路預留,格式不破)。✅
5. **授權過期天數**: 預設 30 天,可調 7–90。✅
6. **Demo 結算**: TRON testnet(Nile)**真實**簽章/broadcast/確認(免費測試幣)。現場需求:demo 當天要有網路 + 測試幣 + 站點錢包設好。✅
7. **管道 B 鏈別**: demo 只放 TRON 一個地址,保持單純;多鏈(BTC / Ethereum)留 v2。✅

---

## 12. 預估實作工時(批准草案後)

比 v0 少(拿掉 session/計題/退款):

| 任務 | 工時 |
|---|---|
| `wallet/donation_format.py` — encode/decode/sign/verify | 0.5 天 |
| `wallet/donate.html` — 捐贈授權網頁 + QR + 直捐地址 | 0.5 天 |
| `bot/donate.py` — `!donate` / `!support` 處理 + 持久化 | 0.5 天 |
| `bot/bot.py` 改造 — 分流 `!donate` / `!support`(`?` 不動) | 0.25 天 |
| `wallet/settle.py` — TRON USDT testnet 結算 | 0.5 天 |
| 端對端 demo + README 更新(含免責 + 捐贈說明) | 0.5 天 |
| **總計** | **~2.75 天** |

---

## 13. 不做這些(明確排除)

- **不把捐贈當存取門檻** —— 問答永遠免費,這是設計核心。
- 不做退款 / escrow 餘額 / 對帳(捐贈是單向贈與)。
- 不寫多 bot 同步結算(目前單站;`station_id` 已為未來預留格式)。
- 不做 KYC / AML(hackathon demo)。
- 不寫真實 escrow smart contract(testnet + simple transfer)。
- 不做 multi-chain(只 TRON;BTC / Ethereum 留 v2)。

---

## 14. Related Memory / Files

- 既有的 mesh + LLM + RAG 在 [[project-survival-copilot]] 紀錄
- 既有的 setup gotchas 在 [[qvac-setup-gotchas]]
- 架構總覽見 `architecture.html` / `architecture.en.html` / `architecture.md`
- 此設計批准後,實作分支建議命名 `wdk-donate`
