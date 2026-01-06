# WD Gateway TTS — Web Client Reference（最小可用）

本資料夾提供一個「官方 reference」的純 HTML/JS Web client，用於完成端到端流程：

`Web client → Orchestrator → SGLang（LLM streaming）→ ws_gateway_tts（WS API v1）→ Web client 播放`

功能：
- 設定 Orchestrator URL / API key
- 一鍵 connect / disconnect
- 送出「使用者問題」後：即時顯示 LLM streaming 文本（`llm_delta`）
- 同時播放 `audio_chunk`（raw PCM16；依 `docs/API.md` 的 v1 定義；也相容少數實作直接回整段 WAV）
- 顯示 debug：`session_id`、`chunk_seq`、`unit_index` 範圍、TTFA、errors、tool_calls（僅顯示不做 TTS）

> 注意：Browser 原生 WebSocket **無法**自訂 `Authorization` header。此 reference 會把 API key 附加到 URL query：`?api_key=...`。若你的部署要求 header 認證，請在 Nginx/Ingress 層注入。

---

## 1. 本機執行（最簡單）

### 1.1 一鍵啟動（Docker Compose）

在專案根目錄：

```powershell
cd sglang-server
cp .env.example .env
docker compose up -d --build
```

打開瀏覽器：
- `http://localhost:8080/`（或 `http://<HOST_IP>:8080/`）

預設 Orchestrator URL：`ws(s)://<host>/chat`

同網域路徑（避免 CORS）：
- `/chat` → Orchestrator WebSocket
- `/api/v1/...` → SGLang API
- `/tts` → ws_gateway_tts WebSocket

> 取樣率提醒：預設 Piper 模型 `zh_CN-huayan-medium` 通常是 `22050Hz`；頁面會嘗試從 `/tts/healthz` 自動帶入 `model_sample_rate`。

（確認可用）

```powershell
curl http://localhost:8080/api/v1/models
```

### 1.2 dev 模式（可選）

你也可以不用 compose 的 `web` 服務，改用本機靜態 server：

```powershell
cd .\web_client
..\.venv\Scripts\python.exe -m http.server 8000
```

打開瀏覽器：
- `http://localhost:8000/`

並在頁面上把 Orchestrator URL 設為 `ws://localhost:9100/chat`（compose 已對外 publish 9100）。

### 1.5 常見問題：瀏覽器顯示「Directory listing」

如果你看到的是 `.env`、`docker-compose.yml`、`nginx/` 之類的清單，代表你在錯的資料夾啟動了 `http.server`（通常是不小心在 `sglang-server/` 下面）。

- 先在命令列按 `Ctrl + C` 停掉 server
- 再確認目前資料夾並重新啟動：

```powershell
Get-Location
cd D:\._vscode2\detection_pose\web_client
..\.venv\Scripts\python.exe -m http.server 8000
```

> 補充：PowerShell 的 `;` 會「就算前面 `cd` 失敗也繼續跑下一個指令」，所以不建議用 `cd web_client; ...` 來寫成一行。

---

## 2. 操作方式

1. `Orchestrator URL`：例如 `ws://localhost:9100/chat`
2. `API Key`：可留空（會附加到 `?api_key=`；若 Orchestrator 設定 `ORCH_API_KEY` 則需填入）
3. `Connect`
4. 在「輸入問題」貼上內容後按 `Send prompt`
5. 你會看到：
   - `LLM transcript` 逐段出現（streaming）
   - 同時持續播放語音（`audio_chunk`）
6. `Cancel`：中止（Orchestrator 會送 `cancel` 給 ws_gateway_tts；並嘗試回傳 `tts_end.cancelled=true`）

---

## 3. 連到 Docker 部署

若你已把 Orchestrator 暴露為：
- `wss://<host>/chat`（Nginx WS upgrade）

則在頁面上設定：
- `Orchestrator URL`：`wss://<host>/chat`
- `API Key`：依部署需求填入

若部署使用 Nginx，請確認 WS upgrade 已開啟（可參考 `docs/DEPLOY.md` 的 Nginx 範例，將 `/chat` 也用同樣方式轉發）。
