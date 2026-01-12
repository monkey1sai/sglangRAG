# Repo Root Entry

Run from repo root:

```powershell
cp .env.example .env
# edit .env and set SGLANG_API_KEY (and HF_TOKEN/SGLANG_MODEL if needed)
powershell -ExecutionPolicy Bypass -File scripts/up.ps1
```

Tip: to reduce repetitive outputs, tune these in `.env`:
- `SGLANG_SYSTEM_PROMPT`
- `SGLANG_TEMPERATURE`, `SGLANG_TOP_P`, `SGLANG_TOP_K`
- `SGLANG_REPETITION_PENALTY`

Tip: 若 `sglang` logs 出現 `RuntimeError: Not enough memory`（多半是 KV cache 需要的 VRAM 不夠），優先調整：
- `.env`：`MAX_MODEL_LEN=2048`（或更低）
- `.env`：`SGLANG_MEM_FRACTION_STATIC=0.95`（不行再試 `0.98`）
- 或改用量化權重：`.env` 設 `SGLANG_LOAD_FORMAT` / `SGLANG_QUANTIZATION`（例如 GGUF）

Tip: to debug `orchestrator/server.py` locally while keeping `web` (nginx) at `http://localhost:8080/`:
1) `docker compose stop orchestrator`
2) set `.env`: `ORCHESTRATOR_UPSTREAM=host.docker.internal:9100`
3) `docker compose up -d --build --force-recreate --no-deps web`
4) VSCode F5 to start local orchestrator (listen on `0.0.0.0:9100`)

---

# SGLang Production Server

本地部署的 SGLang 推論服務，針對 **RTX 4060 Ti 8GB** 優化，支援多人併發與複雜 Tool Use。

## 📋 系統需求

| 項目 | 需求 |
|-----|------|
| **GPU** | NVIDIA RTX 4060 Ti 8GB |
| **驅動** | NVIDIA Driver 525+ |
| **CUDA** | 12.1+ |
| **Docker** | Docker Desktop with WSL2 |
| **RAM** | 16GB+ (建議 32GB) |

## 🚀 快速開始

### 1. 配置環境

```powershell
# 複製環境變數範本
cp .env.example .env

# 編輯 .env，填入必要配置
# 務必設定 SGLANG_API_KEY
```

### 2. 啟動服務

```powershell
powershell -ExecutionPolicy Bypass -File scripts/up.ps1
```

> Compose 會一併啟動：
> - `sglang`：`http://<HOST_IP>:8082/`
> - `ws_gateway_tts`：健康檢查 `http://<HOST_IP>:9000/healthz`
> - `orchestrator`：健康檢查 `http://<HOST_IP>:9100/healthz`，WS `ws://<HOST_IP>:9100/chat`
> - `web`：`http://<HOST_IP>:8080/`（同網域反代：`/api`、`/tts`、`/chat`）
>
> 備註：SGLang 的 `/health` 預期回 `200` 且 body 為空；可用 `curl -i http://localhost:8082/health` 查看狀態碼與 headers。

### 常見錯誤：`container sglang-server is unhealthy`

這通常代表 SGLang 沒有通過 healthcheck（例如模型下載失敗、權限不足、或 GPU OOM）。

請直接執行：

```powershell
docker compose ps
docker compose logs --tail 200 sglang
curl -i http://localhost:8082/health
curl http://localhost:8082/v1/models -H "Authorization: Bearer <SGLANG_API_KEY>"
```

### 啟動中：`curl /health` 可能顯示 `Empty reply from server`

這通常只是代表 **模型還在載入、服務尚未開始 listen**，屬正常現象（尤其首次啟動或更換模型時可能需要數分鐘）。

建議以 Compose 狀態為準：

```powershell
docker compose ps
```

等 `sglang-server` 變成 `healthy` 後再打：

```powershell
curl -i http://localhost:8082/health
```

常見原因：
- `HF_TOKEN` 缺失/無權限 → HuggingFace 模型下載失敗（尤其 Llama/Gemma）
- `.env` 的 `SGLANG_MODEL` 指到不存在或需要授權的 repo
- GPU VRAM 不足 / OOM（看 logs 關鍵字：`OOM`, `CUDA out of memory`）

### 若 Web 頁面卡死/LLM 一直輸出

可在 `.env` 設定 `SGLANG_MAX_TOKENS` 限制輸出長度（預設 `512`），避免模型長時間輸出導致瀏覽器累積大量文字而卡住。

### 遠端 client 直連 SGLang（需帶 SGLANG_API_KEY）

```powershell
curl http://<HOST_IP>:8082/v1/chat/completions `
  -H "Authorization: Bearer <SGLANG_API_KEY>" `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"twinkle-ai/Llama-3.2-3B-F1-Instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"stream\":false}'
```

### 3. 執行壓力測試

```powershell
# 使用專用的基準測試腳本
..\.venv\Scripts\python.exe sglang-server\benchmark_final.py --concurrency 20 --total 50
```

## 🔊 WebSocket 即時 TTS 測試（逐字 / cancel / resume）

此專案可搭配「WS Gateway（對外 WebSocket）」+「Riva TTS（內部 gRPC）」做即時語音串流。

### WS Gateway（預設：Piper 真實語音）

`docker compose up -d --build` 預設會啟用 `Piper`（真實語音）。第一次啟動會自動下載 Piper binary 與預設模型到 Docker named volume（屬正常現象，可能需要幾分鐘）。

> 若你仍聽到「嘟」聲：通常代表 `WS_TTS_ENGINE` 還是 `dummy`，或 Piper 未成功下載/啟動（請看下方驗收與 logs）。

健康檢查：

```powershell
curl http://localhost:9000/healthz
```

（驗收：確認已切到 piper）

```powershell
# engine_resolved 應該是 "piper"（不是 "dummy"）
curl http://localhost:9000/healthz
docker compose logs -f ws_gateway_tts
```

更換 Piper 模型（進階）：
- 方式 A（最簡單）：清空 volume 後重啟（會重新下載預設模型）
  - `docker volume rm sglang_piper-data`（或用 `docker volume ls` 找出實際名稱）
- 方式 B：在 `.env` 改 `PIPER_MODEL` 與對應的 `PIPER_MODEL_ONNX_URL / PIPER_MODEL_ONNX_SHA256 / PIPER_MODEL_JSON_URL / PIPER_MODEL_JSON_SHA256`，重啟 `ws_gateway_tts`

### WS Gateway（切回 Dummy：除錯用）

若你只想驗證協定/鏈路（不需要真實語音），可切回 `DummyTtsEngine`：

```powershell
# .env
WS_TTS_ENGINE=dummy

docker compose up -d --build ws_gateway_tts
```

> 提醒：Piper 模型有固定取樣率；例如 `zh_CN-huayan-medium` 是 `22050Hz`（看同資料夾的 `.onnx.json`）。若前端送 `sample_rate=16000`，Gateway 會報錯且聽不到聲音。

> 若你需要本機直接啟動（開發/除錯）：仍可用 `..\\.venv\\Scripts\\python.exe -m ws_gateway_tts.server`。

### 基本壓測（50 連線、每秒 5 字、10 分鐘）

```powershell
..\.venv\Scripts\python.exe sglang-server\ws_tts_benchmark.py `
  --url ws://localhost:9000/tts `
  --concurrency 50 `
  --cps 5 `
  --duration 600 `
  --scenario mixed `
  --output-json logs/ws_tts_report.json
```

### 只跑 baseline（不注入 cancel / resume / 背壓）

```powershell
..\.venv\Scripts\python.exe sglang-server\ws_tts_benchmark.py --url ws://localhost:9000/tts --scenario baseline
```

## 📦 推薦模型 (RTX 4060 Ti 8GB)

| 模型 | VRAM 用量 | 說明 |
|-----|----------|------|
| `twinkle-ai/Llama-3.2-3B-F1-Instruct` | ~6GB | **預設**（可由 `.env` 的 `SGLANG_MODEL` 覆寫） |
| `Qwen/Qwen2.5-3B-Instruct` | ~6GB | 中英文表現佳 |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~3GB | 輕量且速度極快 |

## 🔧 核心優勢 (SGLang)

1. **RadixAttention**: 自動快取 System Prompt 與 Tool 定義，顯著降低重複請求的延遲。
2. **結構化輸出優化**: 針對 JSON Schema (Function Calling) 有極佳的生成速度。
3. **高效併發**: 連續批次處理 (Continuous Batching) 充分利用 GPU 算力。

## 📁 專案結構

```
.
├── docker-compose.yml      # Docker Compose 配置
├── .env.example            # 環境變數範本
├── sglang-server/benchmark_final.py      # 最終壓力測試與監控腳本
├── sglang-server/benchmark_report.md     # 效能測試報告
├── sglang-server/nginx/                  # Nginx 反向代理配置
└── sglang-server/monitoring/             # Prometheus 監控配置
```

## 📚 文件索引

- `docs/OPERATE.md`：維運、壓測、以及 SGLang 載入/故障排查（含 `twinkle-ai/Llama-3.2-3B-F1-Instruct` 載入流程）
