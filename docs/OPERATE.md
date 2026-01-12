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
powershell -ExecutionPolicy Bypass -File scripts/up.ps1
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

### 5.0 `container sglang-server is unhealthy`

這通常代表 SGLang 沒有通過 healthcheck（例如模型下載失敗、權限不足、或 GPU OOM）。

建議依序執行：

```powershell
docker compose ps
docker compose logs --tail 200 sglang
curl -i http://localhost:8082/health
curl http://localhost:8082/v1/models -H "Authorization: Bearer <SGLANG_API_KEY>"
```

常見原因：
- `HF_TOKEN` 缺失/無權限 → HuggingFace 模型下載失敗（尤其 Llama/Gemma）
- `.env` 的 `SGLANG_MODEL` 指到不存在或需要授權的 repo
- GPU VRAM 不足 / OOM（看 logs 關鍵字：`OOM`, `CUDA out of memory`）

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

### 5.3 SGLang 載入 `twinkle-ai/Llama-3.2-3B-F1-Instruct` 的流程（如何判斷卡在哪）

此 repo 的 `docker-compose.yml` 會把主機路徑掛載到容器內：
- `./sglang-server/models` → `/root/.cache/huggingface`（HuggingFace cache / snapshots / blobs）

因此第一次啟動或換模型時，下載與載入都會反映在 `sglang-server` logs。

#### A) 你應該看到的典型階段（依序）

1) **找/下載 HuggingFace snapshot**
   - log 常見：
     - `Found local HF snapshot ...; skipping download.`
     - 或下載進度（若 cache 不存在）

2) **載入權重（safetensors 分片）**
   - log 常見：
     - `Loading safetensors checkpoint shards: ... 0/2 ... 2/2`
     - `Load weight end. ... mem usage=...`

3) **初始化 KV cache（容易遇到 VRAM 問題的點）**
   - log 常見：
     - `Using KV cache dtype: ...`
     - `KV Cache is allocated. #tokens: ...`
   - 若失敗常見：
     - `RuntimeError: Not enough memory`（KV cache pool 建不起來）

4) **Capture CUDA graph（啟動期間 /health 可能暫時不通）**
   - log 常見：
     - `Capture cuda graph begin...`
     - `Capture cuda graph end...`

5) **服務起來並通過健康檢查**
   - log 常見：
     - `Uvicorn running on http://0.0.0.0:30000`
     - `The server is fired up and ready to roll!`
   - 這時才建議打：
     - `curl -i http://localhost:8082/health`

#### B) 建議的觀察指令（直接定位卡在哪一段）

```powershell
docker compose ps
docker logs --tail 200 sglang-server
```

#### C) 8GB GPU 建議參數（避免 KV cache 記憶體不足）

在 `.env` 建議搭配（可視情況微調）：
- `SGLANG_MODEL=twinkle-ai/Llama-3.2-3B-F1-Instruct`
- `MAX_MODEL_LEN=2048`（先保守；穩定後再升）
- `SGLANG_MEM_FRACTION_STATIC=0.95`（不行再試 `0.98`）
- `SGLANG_KV_CACHE_DTYPE=fp8_e4m3`（降低 KV cache 佔用）

---

### 5.4 Web UI（`http://localhost:8080/`）連得上但「輸出不顯示 / 只出現零星字」的排查

常見根因是：SGLang 對某些請求回 `400`（例如 prompt 太長），orchestrator 走 streaming 時會被中斷，前端只收到非常短的殘片（看起來像沒輸出）。

#### A) 先確認 `orchestrator` 目前用的模型與參數是新的

> 只改 `.env` 不會自動套用到已在跑的容器；需要 `--force-recreate`。

```powershell
docker compose up -d --force-recreate sglang orchestrator web
docker compose ps
```

#### B) 避免 prompt 太長直接 400（建議開自動截斷 + 放大 token budget）

在 `.env` 設定：
- `SGLANG_MAX_TOTAL_TOKENS=4096`
- `SGLANG_ALLOW_AUTO_TRUNCATE=1`

然後重啟：

```powershell
docker compose up -d --force-recreate sglang
```

#### C) 用 API 直接驗收（排除前端因素）

```powershell
curl -i http://localhost:8082/health
curl http://localhost:8082/v1/models -H "Authorization: Bearer <SGLANG_API_KEY>"
```

---

### 5.5 GGUF 量化補充：若出現「亂字/重複字元」建議回退

實測某些 GGUF 版本可能會出現重複或異常 token（例如大量 `1`、`You`、或重複中文字），導致體感像「輸出壞掉」。

建議優先使用：
- 原始 HuggingFace 權重（safetensors）+ `SGLANG_KV_CACHE_DTYPE=fp8_e4m3`

若仍要用 GGUF，建議把 GGUF 當作可選方案並做 A/B 驗證，確認輸出品質可接受再切換到線上流量。

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

