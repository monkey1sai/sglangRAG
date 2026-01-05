# WD 即時語音 AI Gateway（WebSocket + LLM + Streaming TTS）

此專案提供一套「工程可落地」的端到端串流鏈路：

`Web client → Orchestrator → SGLang（LLM streaming）→ ws_gateway_tts（TTS WS API v1）→ Web client 播放`

特點：
- 對外 API 以 `docs/API.md` 的 WebSocket v1 為準（前端可直接照規格實作）
- `Dummy` engine 用於驗證協定、逐字對齊、cancel/resume、背壓
- `Piper` engine 提供真實語音（需自行準備 `piper` 執行檔與模型 `.onnx`）

---

## Quick Start（本機）

### 0) 建立本機資料夾與 `.env`

```powershell
.\scripts\setup_local_dirs.ps1
```

> `.env` 含敏感資訊不會進 Git；請用 `.env.example` 作為唯一範本。

### 1) 啟動 SGLang（Docker）

```powershell
cd .\sglang-server
cp .env.example .env
docker compose up -d
```

### 2) 啟動 ws_gateway_tts（先用 dummy）

```powershell
cd .\sglang-server
$env:WS_TTS_ENGINE="dummy"
$env:WS_TTS_PORT="9000"
..\.venv\Scripts\python.exe -m ws_gateway_tts.server
```

健康檢查：

```powershell
curl http://localhost:9000/healthz
```

### 3) 啟動 Orchestrator

```powershell
cd D:\._vscode2\detection_pose
$env:SGLANG_BASE_URL="http://localhost:8082"
$env:SGLANG_API_KEY="your-sglang-key"
$env:WS_TTS_URL="ws://localhost:9000/tts"
..\.venv\Scripts\python.exe -m orchestrator.server
```

### 4) 啟動 Web client

```powershell
cd .\web_client
..\.venv\Scripts\python.exe -m http.server 8000
```

打開 `http://localhost:8000/`，Orchestrator URL 預設填 `ws://localhost:9100/chat`。

---

## Dummy vs Piper

- `WS_TTS_ENGINE=dummy`：只會回「可播放音訊」，但不是語音（固定音高的「嘟」聲），用於驗證整條串流鏈路。
- `WS_TTS_ENGINE=piper`：真實語音，需提供：
  - `PIPER_BIN`：`piper.exe` 路徑
  - `PIPER_MODEL`：模型 `.onnx` 路徑

---

## 常見問題

- 只有「嘟」聲：代表你在用 `dummy` engine；協定/播放鏈路正常，但尚未接上真實 TTS。
- Piper 無聲/報錯：常見是 **sample rate 不一致**（例如模型 22050Hz，但 client 送 16000）。

---

## 重要文件

- `docs/API.md`：對外 WebSocket API v1（凍結）
- `docs/DEPLOY.md`：部署（Nginx WS upgrade、docker-compose 範例）
- `docs/OPERATE.md`：日常操作與除錯
- `docs/REPO_INIT.md`：Git LFS / repo 初始化流程
- `docs/TPS_TUNING.md`：SGLang tool-use TPS 調校策略

---

## 專案結構（摘要）

```text
.
├── orchestrator/            # Web client ↔ SGLang ↔ ws_gateway_tts
├── sglang-server/           # SGLang docker-compose + ws_gateway_tts
│   └── ws_gateway_tts/
│       └── tts_engines/     # dummy / piper / riva
├── web_client/              # 純 HTML/JS reference client
├── docs/                    # API / deploy / operate / repo init
├── scripts/                 # 開發輔助腳本
├── logs/                    # 本機輸出（不 commit .json）
├── models/                  # (ignored) 模型與權重
└── audio_outputs/           # (ignored) 音檔輸出
```
