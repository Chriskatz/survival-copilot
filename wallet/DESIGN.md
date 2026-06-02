# Voucher 設計草案 — Survival Co-pilot Pay-per-Question

> **狀態**: 草案 v0,**未實作**。本文件供 review,通過後才寫 code。
> **目的**: 在 stock Meshtastic iOS app 不可改的限制下,讓使用者用 WDK 為 LLM 問答付費。
> **不在範圍內**: 改造手機 app、多基地台、賒帳 / 信用模式。

---

## 1. 一句話總結

使用者在山下用網頁(client-side JS + WDK)**預儲值**一張 voucher,進山後在 Meshtastic 第一句話 `!join <voucher>`,bot 驗章 + 登記;後續所有 `?問題` 從這張 voucher 的餘額扣,跑完報「會話結束」。Bot 回到網路後 **批次 settle 到 TRON USDT**。

---

## 2. 為什麼選這個架構

| 限制 | 選擇 |
|---|---|
| Meshtastic iOS app 不可呼叫外部錢包 | 使用者只貼**一次** voucher 字串到 chat |
| LoRa 200 byte/segment 預算 | voucher 設計目標 ≤180 bytes,後續問答不再帶簽章 |
| 鏈上手續費 + 確認時間 | 山上完全離線交換,settlement 延遲到 base station 回網才執行 |
| 我們是 single-base-station | 不用處理跨 bot 同步餘額 |
| Solo hackathon 時程 | 簽章在 issuance,不做 per-question signing(留 hardening 注記) |

---

## 3. 使用者流程

```
山下(有 4G/wifi)              山上(off-grid)               下山(回網)
─────────────────              ──────────────                ──────────
 ① 開 voucher 網頁
 ② 輸入或載入 WDK seed
 ③ 選「儲 50 題($0.50 USDT)」
 ④ WDK client-side 簽 voucher
 ⑤ 複製字串(or QR scan)
                              ⑥ Meshtastic 第一句:
                                 !join VOUCHER_STRING
                              ⑦ bot 回 "OK 50/50 questions"
                              ⑧ 問 "?被蛇咬?"
                              ⑨ bot 回答 + 餘額 49/50
                              ⑩ 持續問 / 餘額減少
                              ⑪ 餘額 0 → bot 回 "用完請山下儲值"
                                                              ⑫ base station 重新上網
                                                              ⑬ bot WDK 批次 settle 已花費的 USDT
                                                              ⑭ 未用完餘額 → 退回使用者
```

---

## 4. Voucher 字串格式

### 4.1 概觀

```
!join v1.<base58 payload>.<base58 sig>
```

- `!join` — 觸發詞,bot 用這個 prefix 分流
- `v1` — schema version,將來改格式不破舊 voucher
- `payload` — 結構化欄位(下節)
- `sig` — 對 payload 的 Ed25519 簽章

### 4.2 Payload 欄位(binary,固定長度)

| 欄位 | 型別 | bytes | 說明 |
|---|---|---|---|
| user_pubkey | Ed25519 public | 32 | 使用者 WDK 衍生身分 |
| voucher_id | random | 8 | 防重放(bot 記得用過的 id) |
| prepaid_questions | uint16 BE | 2 | 預付題數(0-65535) |
| issued_at | uint32 BE | 4 | 簽發時間 unix epoch |
| valid_until | uint32 BE | 4 | 過期時間(建議 30 天) |
| **總計 payload** | | **50 bytes** | |
| signature(Ed25519 對上述 50 bytes) | | 64 | |
| **總計 binary** | | **114 bytes** | |

base58 編碼後 ~156 字元 + `!join v1..` 前綴 ≈ **170 字元**,**安全進 200 byte 預算**。

### 4.3 範例(假資料)

```
!join v1.3JqHJfwQzN1xMr9PRkM4dPfX...wLp.5KBJ8vWxYz...Nf2
```

---

## 5. 簽章與身分

### 5.1 簽章方案
- **Ed25519**: 64-byte sig,verify 快(bot 在 Pi/Mac 上 <1ms),確定性,無 nonce 漏洞。

### 5.2 Key 衍生
- 使用者 WDK seed 衍生 path `m/44'/501'/0'/0'`(Solana convention,Ed25519)— 或 WDK 自家的 path
- voucher 網頁:純 client-side WDK,**seed 不離開瀏覽器**
- bot 端只看 pubkey,**沒有也不需要 user 的私鑰**

### 5.3 為什麼 Ed25519 而非 secp256k1
- Ed25519 sig 64 bytes,secp256k1 (DER) 71-72 bytes — 省 7 bytes
- Ed25519 verify 速度更快
- 結算到 TRON 時,bot 端用另一把 secp256k1 key 簽 USDT tx(不影響 voucher 階段)

---

## 6. Bot 端狀態

### 6.1 In-memory(每次啟動清空)

```python
# session 表
sessions: dict[bytes, Session]  # key = user_pubkey
# 用過的 voucher id(防重放)
used_voucher_ids: set[bytes]
```

```python
@dataclass
class Session:
    user_pubkey: bytes
    meshtastic_node_id: int   # 在 !join 時鎖定,後續只有這 node 能扣 balance
    remaining: int             # 剩餘題數
    voucher_id: bytes
    valid_until: int           # unix epoch
    spent_usd_cents: int       # 累計花費,settle 時用
```

### 6.2 Persistent(SQLite 或 JSON 檔)

`wallet/state.json`(JSON 已夠用,hackathon 時程):

```json
{
  "used_voucher_ids": ["base58...", "..."],
  "pending_settlements": [
    {
      "user_pubkey": "base58...",
      "amount_usd_cents": 47,
      "voucher_id": "base58...",
      "first_use": 1717000000,
      "last_use": 1717003600
    }
  ]
}
```

每次扣款後 atomic 寫檔(同檔名 `.tmp` 寫完 rename)。

---

## 7. Bot 訊息處理變化

```
incoming text:
├── starts with "!join " → voucher.py:handle_join()
│       ├── parse v1.payload.sig
│       ├── verify sig
│       ├── reject if voucher_id 已用過
│       ├── reject if valid_until < now
│       ├── reject if user_pubkey 已有 active session(避免雙開)
│       ├── 建 Session,bind meshtastic_node_id
│       └── reply "OK N/N questions, valid until YYYY-MM-DD"
│
├── starts with "?" → (現有流程,加一步)
│       ├── 找 sender_node_id 對應的 Session
│       ├── 沒 session → reply "no session, send !join first"
│       ├── remaining == 0 → reply "session exhausted"
│       ├── valid_until < now → reply "voucher expired"
│       ├── 否則 LLM call → chunked reply, remaining -=1
│       └── 寫回 state.json
│
└── 其他 → 忽略(maintains 現有 polite-on-shared-mesh 行為)
```

---

## 8. Voucher 網頁(`wallet/voucher_gen.html`)

### 8.1 規格
- 單一 HTML 檔,**離線可用**(全部 JS 內嵌或 `file://`)
- 載 `@tetherto/wdk` + `wdk-wallet-evm`(via CDN 或本地 bundle)
- UI: 4 個欄位 + 1 個按鈕
  1. Mnemonic 輸入 / 產新 seed
  2. 預付題數選擇(滑桿: 10 / 50 / 100 / 500)
  3. 對應 USD 金額自動顯示($0.01/題假設值)
  4. 過期天數(預設 30)
  5. 「Generate Voucher」按鈕 → 產 voucher 字串 + QR(便手機掃)

### 8.2 安全
- Seed phrase **不送任何 server**(無 server,純 static page)
- 提示使用者:**離開頁面後 seed 不會儲存**,要記下 seed 才能下次繼續用
- 強烈建議使用者拿一個專用 seed(只放小額 voucher 用),別用主錢包 seed

---

## 9. Settlement(山下回網時)

### 9.1 Trigger
- Bot 偵測到網路 → 跑 `wallet/settle.py`
- 或手動 `python wallet/settle.py --dry-run` 先看

### 9.2 流程
```
for entry in pending_settlements:
    bot 用自己的 TRON USDT wallet 算出 owed_amount
    對使用者 wallet 發 USDT transfer (從預付 escrow)
    或：bot 持有的是 user signed pre-authorized tx,broadcast 之
    收到鏈上 confirmation → 從 pending 移除
```

### 9.3 預付 vs 信用
本草案假設 **預付**:voucher 階段使用者已把 USDT 轉到 bot 控制的 escrow 地址。
但 hackathon demo 可簡化:**完全 mock settle**,demo 影片上演「假裝 settled $0.47」。
真實 escrow 機制留 v2。

---

## 10. 安全考量

### 10.1 已防護
| 攻擊 | 對策 |
|---|---|
| 重放(把舊 voucher 拿來再用) | `used_voucher_ids` 集合 |
| 偽造 voucher | Ed25519 簽章,bot 驗 user_pubkey 配 sig |
| 過期 voucher | `valid_until` 強制檢查 |
| 雙開 session(同 voucher 從兩處 join) | bot 拒絕已 active 的 user_pubkey |

### 10.2 已知弱項(hackathon 接受 / 留 v2)
| 弱項 | 影響 | 為什麼接受 |
|---|---|---|
| **Meshtastic node ID 可偽造** | 攻擊者偽造受害者 node ID 用掉他的餘額 | 需要對方在 BLE 範圍內;且 hackathon scope 之外 |
| **bot 是中心化信任點** | bot 拒答後 user 無補救 | hackathon 是 single-base-station demo |
| **無單題 sig** | 看到 !join 後任何人在那 node ID 發 ? 都能扣 | 同上;v2 可加 per-question sig 約多 88 chars/題 |
| **Settlement 信任 bot** | bot 可少報花費 / 多收 | 預付模式自然限縮損失;真實 prod 需要鏈上 escrow 合約 |

### 10.3 DoS 性質
- 攻擊者送大量假 voucher → bot 每個都要 verify sig(~1ms each)。1000 假 voucher/秒 才會塞住 Mac。**LoRa airtime 本身就是天然 rate limiter**,不擔心。

---

## 11. 開放問題(請 review 時回覆)

1. **單題定價**: 提議 $0.01 USDT。要不要按 LLM token 數動態定價?(複雜 → 我傾向不要)
2. **過期天數**: 提議預設 30 天,可調 7-90。OK?
3. **未用完餘額是否退**: 提議 settlement 時退回使用者地址。或不退、bot 留下?
4. **WDK seed 產生方式**: voucher 網頁產新 seed vs 要使用者貼既有 seed?提議「都可以」,但預設新 seed(更安全)。
5. **Voucher 網頁 host**: 純 `file://` 開啟 vs 要不要 host 在 GitHub Pages?提議 `file://` 給示範 + 印一份 PDF 給使用者帶。
6. **demo 結算是否真的上鏈**?提議 demo 用 TRON testnet(Nile)— 真實簽章、真實 broadcast、真實確認,但用測試幣。比 mock 帥很多,且 testnet 免費。
7. **設定 USDT 計價的浮動**:1 USDT = 1 USD 假定,不處理匯率變動。OK?

---

## 12. 預估實作工時(批准草案後)

| 任務 | 工時 |
|---|---|
| `wallet/voucher_format.py` — encode/decode/sign/verify | 0.5 天 |
| `wallet/voucher_gen.html` — 產 voucher 網頁 | 0.5 天 |
| `bot/payment.py` — session 管理 + 持久化 | 0.5 天 |
| `bot/bot.py` 改造 — 整合 !join 跟 ? 處理 | 0.5 天 |
| `wallet/settle.py` — TRON USDT testnet 結算 | 0.5 天 |
| 端對端 demo 測試 + README 更新 | 0.5 天 |
| **總計** | **3 天**(比先前估的 1.5 天保守) |

---

## 13. 不做這些(明確排除)

- 不寫多 bot 同步(只有 1 個 base station)
- 不做 voucher 轉讓(voucher 綁定 user pubkey)
- 不寫 voucher 退款 UI(指令列 settle.py 就好)
- 不做 KYC / AML(this is a hackathon demo)
- 不寫真實的 escrow smart contract(用測試幣 + simple transfer)
- 不做 multi-chain(只 TRON,L1 BTC / Ethereum 留 v2)

---

## 14. Related Memory / Files

- 既有的 mesh + LLM 在 [[project-survival-copilot]] 紀錄
- 既有的 setup gotchas 在 [[qvac-setup-gotchas]]
- 此設計批准後,實作分支建議命名 `wdk-voucher`
