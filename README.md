# Repo Root Entry

Run from repo root:

```powershell
cp .env.example .env
# edit .env and set SGLANG_API_KEY (and HF_TOKEN if needed)
docker compose up -d --build
```

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
docker compose up -d --build
```

> Compose 會一併啟動：
> - `sglang`：`http://<HOST_IP>:8082/`
> - `ws_gateway_tts`：健康檢查 `http://<HOST_IP>:9000/healthz`
> - `orchestrator`：健康檢查 `http://<HOST_IP>:9100/healthz`，WS `ws://<HOST_IP>:9100/chat`
> - `web`：`http://<HOST_IP>:8080/`（同網域反代：`/api`、`/tts`、`/chat`）
>
> 備註：SGLang 的 `/health` 預期回 `200` 且 body 為空；可用 `curl -i http://localhost:8082/health` 查看狀態碼與 headers。

### 遠端 client 直連 SGLang（需帶 SGLANG_API_KEY）

```powershell
curl http://<HOST_IP>:8082/v1/chat/completions `
  -H "Authorization: Bearer <SGLANG_API_KEY>" `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"Qwen/Qwen2.5-1.5B-Instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"stream\":false}'
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
| `Qwen/Qwen2.5-3B-Instruct` | ~6GB | 中英文表現佳 |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~3GB | **預設**，輕量且速度極快 |

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
