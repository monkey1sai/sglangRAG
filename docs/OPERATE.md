# WD 即時語音 AI Gateway — 維運與壓測指南

本文件提供：
- 如何使用 `ws_tts_benchmark.py` 做 baseline / mixed 壓測
- 如何判讀 TTFA / UnitLatency / errors / 缺漏
- 常見故障排查

---

## 1. 服務啟動（本機/維運最小流程）

(option A: Docker Compose)

```powershell
cp .env.example .env
docker compose up -d --build
```

(option B: run ws_gateway_tts manually for dev/debug)

```powershell
cd sglang-server
$env:WS_TTS_ENGINE="dummy"
$env:WS_TTS_PORT="9000"
..\.venv\Scripts\python.exe -m ws_gateway_tts.server
```

健康檢查：

```powershell
curl http://localhost:9000/healthz
```

---

## 2. 壓測：baseline / mixed

### 2.1 baseline（不注入斷線/cancel/背壓）

```powershell
..\.venv\Scripts\python.exe ws_tts_benchmark.py --url ws://localhost:9000/tts --scenario baseline --concurrency 50 --cps 5 --duration 60 --output-json logs/ws_tts_baseline_50c_60s.json
```

### 2.2 mixed（注入 disconnect/cancel/backpressure）

```powershell
..\.venv\Scripts\python.exe ws_tts_benchmark.py --url ws://localhost:9000/tts --scenario mixed --concurrency 50 --cps 5 --duration 60 --output-json logs/ws_tts_mixed_50c_60s.json
```

### 2.3 慢 client（加重背壓）

```powershell
..\.venv\Scripts\python.exe ws_tts_benchmark.py --url ws://localhost:9000/tts --scenario mixed --concurrency 50 --cps 5 --duration 60 --backpressure-percent 0.3 --backpressure-pause-s 10 --disconnect-percent 0.1 --cancel-percent 0.1 --output-json logs/ws_tts_mixed_50c_60s_heavy.json
```

---

## 3. 判讀指標（如何判定穩定）

### 3.1 正確性（必須先過）

- `errors session`：baseline 應接近 0；mixed 可接受少量（但應與注入比例一致，不應連鎖擴大）
- `missing_units / duplicate_units / mismatched_units`：應為 0 或非常低
- `sent_units == received_units`：baseline 應成立；mixed 若發生斷線/取消，需對照注入比例與錯誤型態判讀

### 3.2 延遲（TTFA / UnitLatency）

- TTFA（首段音訊延遲）：
  - 觀察 p95/p99 是否隨併發或時間逐步惡化
- UnitLatency（每字延遲）：
  - p95/p99 長尾主要用來看「排隊」或「flush 粒度」效應

---

## 4. 三種常見型態：如何歸因

### 4.1 server-side bottleneck（排隊/事件迴圈卡住）

典型訊號：
- 併發增加時，TTFA 與 UnitLatency 的 p95/p99 **一起**非線性上升
- mixed 情境下 errors 可能開始增加（例如 internal error / timeouts）
- 服務端 CPU/記憶體持續上升且不回落（需搭配 OS/容器監控）

建議動作：
- 固定 text-file 與 cps，做 concurrency 梯度（10→25→50）對照斜率

### 4.2 backpressure（慢 client 拖累）

典型訊號：
- `errors` 中出現 `backpressure`
- heavy backpressure 測試下，應「局部出錯、全局仍穩」：其他 session 的 missing 不應飆升

建議動作：
- 提高 `--backpressure-percent` 與 `--backpressure-pause-s`，觀察 errors 型態是否仍可控

### 4.3 量測假象（chunk / flush 粒度）

背景：
- Gateway 不保證逐字音訊，音訊以 chunk/flush 粒度產出。

典型訊號：
- `errors=0`、`missing=0`，但 UnitLatency p95/p99 很長尾
- TTFA 相對穩定，但 UnitLatency 長尾受「標點密度 / max_pending_units / text_end」影響顯著
- 同一份 text-file 下，改變 `cps` 時 UnitLatency 長尾會顯著變化

建議動作：
- 固定 concurrency/duration/cps，只換 text-file（高標點 vs 低標點）做對照

---

## 5. 常見故障排查（最常遇到）

### 5.1 `--duration 60` 但實際提早結束

原因通常是：**文字送完了**，benchmark 會提早送 `text_end` 並結束 session。

處置：
- 使用 `--text-file`，確保文字長度至少 `cps * duration`（例如 cps=5、duration=60，至少 300 字/units）
- 若要更保險，建議準備 350～600 字，且結尾以 `。` 收尾

### 5.2 mixed 出現 `resume_not_available`

原因通常是：
- 斷線超過快取窗、或 last_unit_index_received 不在可續傳範圍

處置：
- 降低 `--reconnect-delay-s` 或降低斷線比例
- client 在收到 `resume_not_available` 後改走「重新 start 新 session」

---

## 6. 最小驗收 Checklist（維運/壓測）

- baseline-50（60 秒）：
  - `errors session = 0`
  - `missing/duplicate/mismatched = 0`
  - `sent_units == received_units`
  - TTFA/UnitLatency p99 不隨時間惡化（至少在 60 秒內保持穩定）
- mixed-50（60 秒，預設注入）：
  - errors 類型合理（主要為 backpressure / 斷線重連相關），不出現大量 `internal_error`
  - 沒有大規模 missing/duplicate/mismatch
- heavy backpressure：
  - 慢 client 被正確隔離（局部 error），其他 session 仍穩定

