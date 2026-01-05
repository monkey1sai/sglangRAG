# Orchestrator（Web client ↔ SGLang ↔ ws_gateway_tts）

此服務負責「安全邊界 + 端到端串流」：
- 前端只連 Orchestrator（不持有任何 SGLang API key）
- Orchestrator 以 streaming 呼叫 SGLang（`/v1/chat/completions`）
- 每個 `delta.content` 會：
  - 立即轉送給前端（`type=llm_delta`）
  - 同時依 buffering 規則轉成 ws_gateway_tts 的 `text_delta`，產生 `audio_chunk`

> 注意：Orchestrator 轉送給前端的 `audio_chunk / start_ack / tts_end / error` 欄位完全保持 ws_gateway_tts 的 WS API v1 schema，不做改名或自創欄位。

---

## 1. 啟動（本機）

在專案根目錄：

```powershell
$env:SGLANG_BASE_URL="http://localhost:8082"
$env:SGLANG_API_KEY="your-sglang-key"
$env:SGLANG_MODEL="Qwen/Qwen2.5-1.5B-Instruct"
$env:WS_TTS_URL="ws://localhost:9000/tts"
..\.venv\Scripts\python.exe -m orchestrator.server
```

端點：
- WebSocket：`ws://localhost:9100/chat`
- 健康檢查：`http://localhost:9100/healthz`

---

## 2. 環境變數

| env var | 預設 | 說明 |
|---|---:|---|
| `ORCH_HOST` | `0.0.0.0` | listen host |
| `ORCH_PORT` | `9100` | listen port |
| `ORCH_API_KEY` | (空) | 若設定，前端需帶 `?api_key=` 或 `Authorization: Bearer` |
| `SGLANG_BASE_URL` | `http://localhost:8082` | SGLang base URL |
| `SGLANG_API_KEY` | (必填) | SGLang API key（只在後端） |
| `SGLANG_MODEL` | `Qwen/Qwen2.5-1.5B-Instruct` | 模型名稱 |
| `WS_TTS_URL` | `ws://localhost:9000/tts` | ws_gateway_tts 的 WS 端點 |
| `WS_TTS_API_KEY` | (空) | ws_gateway_tts 的 Bearer key（若有） |
| `TTS_FLUSH_MIN_CHARS` | `12` | delta->TTS buffering：累積到此字數才送一次 `text_delta` |
| `TTS_FLUSH_ON_PUNCT` | `true` | 遇到標點（見程式內 `PUNCTUATION`）就立刻送 `text_delta` |
| `ALLOW_CLIENT_TTS_URL` | `false` | 允許前端在 request 中覆寫 `ws_tts_url`（僅建議本機除錯） |

