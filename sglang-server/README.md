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
docker compose up -d
```

### 3. 執行壓力測試

```powershell
# 使用專用的基準測試腳本
..\.venv\Scripts\python.exe benchmark_final.py --concurrency 20 --total 50
```

## 🔊 WebSocket 即時 TTS 測試（逐字 / cancel / resume）

此專案可搭配「WS Gateway（對外 WebSocket）」+「Riva TTS（內部 gRPC）」做即時語音串流。

### 啟動 WS Gateway（MVP）

預設先用 `DummyTtsEngine`（會產生可播放音訊，但不是真實語音），用來驗證逐字對齊 / cancel / resume / 背壓流程。

```powershell
cd sglang-server
$env:WS_TTS_ENGINE="dummy"
$env:WS_TTS_PORT="9000"
..\.venv\Scripts\python.exe -m ws_gateway_tts.server
```

> 若你接上喇叭只聽到「嘟」聲：這是 DummyTTS 的預期行為（固定音高），代表協定與播放鏈路正常，但尚未整合真實 TTS。

### 啟動 WS Gateway（Piper：真實語音 / 開源可本地部署）

Piper 是開源 TTS，適合做本地部署與商用（需自行下載模型與 piper CLI）。

```powershell
cd sglang-server
$env:WS_TTS_ENGINE="piper"
$env:PIPER_BIN="C:\\path\\to\\piper.exe"
$env:PIPER_MODEL="C:\\path\\to\\zh\\model.onnx"
$env:WS_TTS_PORT="9000"
..\.venv\Scripts\python.exe -m ws_gateway_tts.server
```

> 提醒：Piper 模型有固定取樣率；例如 `zh_CN-huayan-medium` 是 `22050Hz`（看同資料夾的 `.onnx.json`）。若前端送 `sample_rate=16000`，Gateway 會報錯且聽不到聲音。

健康檢查：

```powershell
curl http://localhost:9000/healthz
```

### 基本壓測（50 連線、每秒 5 字、10 分鐘）

```powershell
..\.venv\Scripts\python.exe ws_tts_benchmark.py `
  --url ws://localhost:9000/tts `
  --concurrency 50 `
  --cps 5 `
  --duration 600 `
  --scenario mixed `
  --output-json logs/ws_tts_report.json
```

### 只跑 baseline（不注入 cancel / resume / 背壓）

```powershell
..\.venv\Scripts\python.exe ws_tts_benchmark.py --url ws://localhost:9000/tts --scenario baseline
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
sglang-server/
├── docker-compose.yml      # Docker Compose 配置
├── .env.example            # 環境變數範本
├── benchmark_final.py      # 最終壓力測試與監控腳本
├── benchmark_report.md     # 效能測試報告
├── nginx/                  # Nginx 反向代理配置
└── monitoring/             # Prometheus 監控配置
```
