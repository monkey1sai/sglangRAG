diff --git a/.gitignore b/.gitignore
index 65479e5..9b97a57 100644
--- a/.gitignore
+++ b/.gitignore
@@ -13,6 +13,11 @@ env/
 dist/
 build/
 
+# Env (secrets)
+.env
+.env.*
+!.env.example
+
 # IDEs
 .vscode/
 .idea/
@@ -24,6 +29,24 @@ build/
 Thumbs.db
 desktop.ini
 
+# Logs / outputs
+logs/*.json
+*.log
+
+# Audio artifacts
+*.wav
+*.pcm
+*.mp3
+audio_outputs/**
+!audio_outputs/.gitignore
+
+# Models (never commit)
+models/**
+!models/.gitignore
+
+# Local vendor binaries (keep public repo clean)
+piper/
+
 # vLLM Server - Runtime files
 vllm-server/models/
 vllm-server/logs/
@@ -31,7 +54,7 @@ vllm-server/certs/
 vllm-server/.env
 
 # Docker
-*.log
+# (handled above)
 
 # Temp files
 *.tmp
diff --git a/README.md b/README.md
index ab0185a..dba37d2 100644
--- a/README.md
+++ b/README.md
@@ -1,46 +1,108 @@
-# TPS 調整策略（SGLang Tool Use 基準）
+# WD 即時語音 AI Gateway（WebSocket + LLM + Streaming TTS）
 
-本文件整理「以提升 TPS 為主」的調整策略，適用於 `sglang-server/benchmark_50_tools_tps.py` 這類工具呼叫壓測腳本。
+此專案提供一套「工程可落地」的端到端串流鏈路：
+
+`Web client → Orchestrator → SGLang（LLM streaming）→ ws_gateway_tts（TTS WS API v1）→ Web client 播放`
+
+特點：
+- 對外 API 以 `docs/API.md` 的 WebSocket v1 為準（前端可直接照規格實作）
+- `Dummy` engine 用於驗證協定、逐字對齊、cancel/resume、背壓
+- `Piper` engine 提供真實語音（需自行準備 `piper` 執行檔與模型 `.onnx`）
 
 ---
 
-## 影響 TPS 的關鍵因素
-- **tool schema 長度**：tools 定義越長，prompt 越大，TPS 越低。
-- **tools 數量**：工具越多，模型選擇成本越高，TPS 越低。
-- **輸出長度**：回答或 tool_call 參數越長，TPS 越低。
-- **模式與策略**：`tool_choice`、`max_tokens`、stream 模式會直接影響 TPS。
+## Quick Start（本機）
+
+### 0) 建立本機資料夾與 `.env`
+
+```powershell
+.\scripts\setup_local_dirs.ps1
+```
+
+> `.env` 含敏感資訊不會進 Git；請用 `.env.example` 作為唯一範本。
+
+### 1) 啟動 SGLang（Docker）
+
+```powershell
+cd .\sglang-server
+cp .env.example .env
+docker compose up -d
+```
+
+### 2) 啟動 ws_gateway_tts（先用 dummy）
+
+```powershell
+cd .\sglang-server
+$env:WS_TTS_ENGINE="dummy"
+$env:WS_TTS_PORT="9000"
+..\.venv\Scripts\python.exe -m ws_gateway_tts.server
+```
+
+健康檢查：
+
+```powershell
+curl http://localhost:9000/healthz
+```
+
+### 3) 啟動 Orchestrator
+
+```powershell
+cd D:\._vscode2\detection_pose
+$env:SGLANG_BASE_URL="http://localhost:8082"
+$env:SGLANG_API_KEY="your-sglang-key"
+$env:WS_TTS_URL="ws://localhost:9000/tts"
+..\.venv\Scripts\python.exe -m orchestrator.server
+```
+
+### 4) 啟動 Web client
+
+```powershell
+cd .\web_client
+..\.venv\Scripts\python.exe -m http.server 8000
+```
+
+打開 `http://localhost:8000/`，Orchestrator URL 預設填 `ws://localhost:9100/chat`。
 
 ---
 
-## 最高優先的 TPS 提升策略
-1. **降低 tools 數量**：建議 8–12 個工具為一組壓測集。
-2. **精簡 tool schema**：移除不必要欄位（例如 `settings` 詳細參數）。
-3. **限制輸出長度**：降低 `max_tokens`（例如 32–80）。
-4. **避免自由回答**：全部請求都以工具操作為主，減少自然語言輸出。
-5. **強制 tool 呼叫**：`tool_choice = "required"` 可避免回覆文字拉低 TPS。
-6. **動態裁剪工具**：依請求關鍵字只傳對應工具，縮短 prompt。
+## Dummy vs Piper
+
+- `WS_TTS_ENGINE=dummy`：只會回「可播放音訊」，但不是語音（固定音高的「嘟」聲），用於驗證整條串流鏈路。
+- `WS_TTS_ENGINE=piper`：真實語音，需提供：
+  - `PIPER_BIN`：`piper.exe` 路徑
+  - `PIPER_MODEL`：模型 `.onnx` 路徑
 
 ---
 
-## 目前基準腳本設定（摘要）
-檔案：`sglang-server/benchmark_50_tools_tps.py`
-- `TOOL_COUNT = 12`
-- `tool_choice = "required"`
-- `max_tokens = 80`
-- tool schema 已精簡（無 `settings` 內部參數）
-- 只產生工具導向請求（無一般問答）
-- 依關鍵字動態裁剪 tools
+## 常見問題
+
+- 只有「嘟」聲：代表你在用 `dummy` engine；協定/播放鏈路正常，但尚未接上真實 TTS。
+- Piper 無聲/報錯：常見是 **sample rate 不一致**（例如模型 22050Hz，但 client 送 16000）。
 
 ---
 
-## 測試方式
-```powershell
-.venv\Scripts\python.exe sglang-server\benchmark_50_tools_tps.py --concurrency 1 --total 5 --no-stream
-```
+## 重要文件
+
+- `docs/API.md`：對外 WebSocket API v1（凍結）
+- `docs/DEPLOY.md`：部署（Nginx WS upgrade、docker-compose 範例）
+- `docs/OPERATE.md`：日常操作與除錯
+- `docs/REPO_INIT.md`：Git LFS / repo 初始化流程
+- `docs/TPS_TUNING.md`：SGLang tool-use TPS 調校策略
 
 ---
 
-## 取捨與建議
-- **TPS 優先**：降低 tools 數量 + 簡化 schema + 強制 tool。
-- **準確度優先**：保留更多工具與完整參數，但 TPS 會下降。
-- 建議區分 **TPS profile** 與 **Accuracy profile**，分別測量。
+## 專案結構（摘要）
+
+```text
+.
+├── orchestrator/            # Web client ↔ SGLang ↔ ws_gateway_tts
+├── sglang-server/           # SGLang docker-compose + ws_gateway_tts
+│   └── ws_gateway_tts/
+│       └── tts_engines/     # dummy / piper / riva
+├── web_client/              # 純 HTML/JS reference client
+├── docs/                    # API / deploy / operate / repo init
+├── scripts/                 # 開發輔助腳本
+├── logs/                    # 本機輸出（不 commit .json）
+├── models/                  # (ignored) 模型與權重
+└── audio_outputs/           # (ignored) 音檔輸出
+```
diff --git a/docs/DEPLOY.md b/docs/DEPLOY.md
index c7547d5..89bed83 100644
--- a/docs/DEPLOY.md
+++ b/docs/DEPLOY.md
@@ -26,9 +26,21 @@
 |---|---:|---|
 | `WS_TTS_HOST` | `0.0.0.0` | Gateway 綁定位址 |
 | `WS_TTS_PORT` | `9000` | Gateway 對外 port |
-| `WS_TTS_ENGINE` | `dummy` | `dummy` / `riva` |
+| `WS_TTS_ENGINE` | `dummy` | `dummy` / `piper` / `riva` |
 | `RIVA_SERVER` | `localhost:50051` | 使用 `riva` engine 時的 gRPC 位址 |
 
+### Piper（真實語音 / 開源可本地部署）
+
+> Piper 需要你自行提供 piper CLI 與模型檔（.onnx）；本專案只提供 adapter。
+
+| env var | 預設 | 說明 |
+|---|---:|---|
+| `PIPER_BIN` | (必填) | `piper` 可執行檔路徑 |
+| `PIPER_MODEL` | (必填) | Piper 模型 `.onnx` 路徑 |
+| `PIPER_SPEAKER_ID` | (空) | 多說話人模型用 |
+| `PIPER_EXTRA_ARGS` | (空) | 直接追加到 piper CLI 的參數（進階） |
+| `PIPER_OUTPUT_MODE` | `file` | `file`（較穩）或 `stdout`（若你的 piper 支援 `--output_file -`） |
+
 建議（產品化）：
 - `GATEWAY_API_KEY`（或 JWT 設定）用於 WS 認證
 - per-tenant concurrency limit / rate limit 設定（視實作而定）
@@ -128,4 +140,3 @@ server {
 - Browser/benchmark 可連上 `ws://localhost:9000/tts`
 - Nginx 轉發後可連上 `wss://<host>/tts`（WS upgrade 正常）
 - 服務重啟後可自動恢復（`restart: unless-stopped` 或 systemd）
-
diff --git a/sglang-server/README.md b/sglang-server/README.md
index e4d0704..7514983 100644
--- a/sglang-server/README.md
+++ b/sglang-server/README.md
@@ -52,6 +52,23 @@ $env:WS_TTS_PORT="9000"
 ..\.venv\Scripts\python.exe -m ws_gateway_tts.server
 ```
 
+> 若你接上喇叭只聽到「嘟」聲：這是 DummyTTS 的預期行為（固定音高），代表協定與播放鏈路正常，但尚未整合真實 TTS。
+
+### 啟動 WS Gateway（Piper：真實語音 / 開源可本地部署）
+
+Piper 是開源 TTS，適合做本地部署與商用（需自行下載模型與 piper CLI）。
+
+```powershell
+cd sglang-server
+$env:WS_TTS_ENGINE="piper"
+$env:PIPER_BIN="C:\\path\\to\\piper.exe"
+$env:PIPER_MODEL="C:\\path\\to\\zh\\model.onnx"
+$env:WS_TTS_PORT="9000"
+..\.venv\Scripts\python.exe -m ws_gateway_tts.server
+```
+
+> 提醒：Piper 模型有固定取樣率；例如 `zh_CN-huayan-medium` 是 `22050Hz`（看同資料夾的 `.onnx.json`）。若前端送 `sample_rate=16000`，Gateway 會報錯且聽不到聲音。
+
 健康檢查：
 
 ```powershell
diff --git a/sglang-server/ws_gateway_tts/server.py b/sglang-server/ws_gateway_tts/server.py
index 295096d..2e070b5 100644
--- a/sglang-server/ws_gateway_tts/server.py
+++ b/sglang-server/ws_gateway_tts/server.py
@@ -21,6 +21,7 @@ from .protocol import (
 from .session import SessionManager
 from .tts_engines.base import AudioSpec
 from .tts_engines.dummy import DummyTtsEngine
+from .tts_engines.piper import PiperTtsEngine
 from .tts_engines.riva import RivaTtsEngine
 
 
@@ -171,17 +172,19 @@ def build_wav_header(*, sample_rate: int, channels: int) -> bytes:
 def build_engine() -> Any:
     engine_name = os.getenv("WS_TTS_ENGINE", "dummy").lower().strip()
     if engine_name == "dummy":
-        return DummyTtsEngine()
+        return engine_name, DummyTtsEngine()
+    if engine_name == "piper":
+        return engine_name, PiperTtsEngine.from_env()
     if engine_name == "riva":
         server = os.getenv("RIVA_SERVER", "localhost:50051")
-        return RivaTtsEngine(server=server)
+        return engine_name, RivaTtsEngine(server=server)
     raise ValueError(f"未知 WS_TTS_ENGINE: {engine_name}")
 
 
 class GatewayApp:
     def __init__(self) -> None:
         self.started_at_utc = dt.datetime.now(dt.timezone.utc)
-        self.engine = build_engine()
+        self.engine_name, self.engine = build_engine()
         self.sessions = SessionManager(self.engine)
         self._cleanup_task: Optional[asyncio.Task[None]] = None
         self.metrics = Metrics()
@@ -204,6 +207,7 @@ class GatewayApp:
             {
                 "status": "ok",
                 "engine": os.getenv("WS_TTS_ENGINE", "dummy"),
+                "engine_resolved": self.engine_name,
                 "version": os.getenv("WS_TTS_VERSION", "dev"),
                 "started_at": self.started_at_utc.isoformat(),
                 "uptime_s": uptime_s,
diff --git a/web_client/README.md b/web_client/README.md
index 8bf7e1e..22f4640 100644
--- a/web_client/README.md
+++ b/web_client/README.md
@@ -1,19 +1,23 @@
 # WD Gateway TTS — Web Client Reference（最小可用）
 
-本資料夾提供一個「官方 reference」的純 HTML/JS Web client，用於：
-- 設定 gateway URL / API key
+本資料夾提供一個「官方 reference」的純 HTML/JS Web client，用於完成端到端流程：
+
+`Web client → Orchestrator → SGLang（LLM streaming）→ ws_gateway_tts（WS API v1）→ Web client 播放`
+
+功能：
+- 設定 Orchestrator URL / API key
 - 一鍵 connect / disconnect
-- 送出 `start`、`text_delta`、`text_end`、`cancel`
-- 播放 `audio_chunk`（raw PCM16，依 `audio_format=pcm16_wav` 的 v1 定義）
-- 顯示 debug：`session_id`、`chunk_seq`、`unit_index` 範圍、TTFA、errors
+- 送出「使用者問題」後：即時顯示 LLM streaming 文本（`llm_delta`）
+- 同時播放 `audio_chunk`（raw PCM16；依 `docs/API.md` 的 v1 定義；也相容少數實作直接回整段 WAV）
+- 顯示 debug：`session_id`、`chunk_seq`、`unit_index` 範圍、TTFA、errors、tool_calls（僅顯示不做 TTS）
 
-> 注意：Browser 原生 WebSocket **無法**自訂 `Authorization` header。此 reference 會把 API key 附加到 URL query：`?api_key=...`。若你的部署要求 `Authorization: Bearer ...`，請在 Nginx/Ingress 層把 query 轉成 header（或調整 Gateway 認證方式）。
+> 注意：Browser 原生 WebSocket **無法**自訂 `Authorization` header。此 reference 會把 API key 附加到 URL query：`?api_key=...`。若你的部署要求 header 認證，請在 Nginx/Ingress 層注入。
 
 ---
 
 ## 1. 本機執行（最簡單）
 
-### 1.1 啟動 Gateway（dummy）
+### 1.1 啟動 ws_gateway_tts（dummy）
 
 在專案根目錄：
 
@@ -24,7 +28,37 @@ $env:WS_TTS_PORT="9000"
 ..\.venv\Scripts\python.exe -m ws_gateway_tts.server
 ```
 
-### 1.2 啟動靜態網站
+### 1.2 啟動 SGLang（Docker）
+
+在專案根目錄：
+
+```powershell
+cd sglang-server
+cp .env.example .env
+docker compose up -d
+```
+
+（確認可用）
+
+```powershell
+curl http://localhost:8082/v1/models
+```
+
+### 1.3 啟動 Orchestrator
+
+在專案根目錄：
+
+```powershell
+cd D:\._vscode2\detection_pose
+$env:SGLANG_BASE_URL="http://localhost:8082"
+$env:SGLANG_API_KEY="your-sglang-key"
+$env:WS_TTS_URL="ws://localhost:9000/tts"
+..\.venv\Scripts\python.exe -m orchestrator.server
+```
+
+預設 Orchestrator：`ws://localhost:9100/chat`
+
+### 1.4 啟動靜態網站
 
 在專案根目錄：
 
@@ -37,7 +71,7 @@ cd .\web_client
 打開瀏覽器：
 - `http://localhost:8000/`
 
-### 1.3 常見問題：瀏覽器顯示「Directory listing」
+### 1.5 常見問題：瀏覽器顯示「Directory listing」
 
 如果你看到的是 `.env`、`docker-compose.yml`、`nginx/` 之類的清單，代表你在錯的資料夾啟動了 `http.server`（通常是不小心在 `sglang-server/` 下面）。
 
@@ -56,24 +90,24 @@ cd D:\._vscode2\detection_pose\web_client
 
 ## 2. 操作方式
 
-1. `Gateway URL`：例如 `ws://localhost:9000/tts`
-2. `API Key`：可留空（會附加到 `?api_key=`）
-3. `Connect + Start`：會建立 WS 並立即送 `start`
-4. 在「輸入文字」貼上內容後按 `Send text_delta`
-   - `逐段`：一次送整段（單一 `text_delta`）
-   - `逐字`：每字一個 `text_delta`（用於逐字互動/除錯）
-5. 按 `Send text_end`：讓 server flush pending units，最後送 `tts_end` 並關閉連線
-6. `Send cancel`：中止並收到 `tts_end.cancelled=true`
+1. `Orchestrator URL`：例如 `ws://localhost:9100/chat`
+2. `API Key`：可留空（會附加到 `?api_key=`；若 Orchestrator 設定 `ORCH_API_KEY` 則需填入）
+3. `Connect`
+4. 在「輸入問題」貼上內容後按 `Send prompt`
+5. 你會看到：
+   - `LLM transcript` 逐段出現（streaming）
+   - 同時持續播放語音（`audio_chunk`）
+6. `Cancel`：中止（Orchestrator 會送 `cancel` 給 ws_gateway_tts；並嘗試回傳 `tts_end.cancelled=true`）
 
 ---
 
 ## 3. 連到 Docker 部署
 
-若你已把 Gateway 暴露為：
-- `wss://<host>/tts`（Nginx WS upgrade）
+若你已把 Orchestrator 暴露為：
+- `wss://<host>/chat`（Nginx WS upgrade）
 
 則在頁面上設定：
-- `Gateway URL`：`wss://<host>/tts`
+- `Orchestrator URL`：`wss://<host>/chat`
 - `API Key`：依部署需求填入
 
-若部署使用 Nginx，請確認 WS upgrade 已開啟（參考 `docs/DEPLOY.md` 的 Nginx 範例）。
+若部署使用 Nginx，請確認 WS upgrade 已開啟（可參考 `docs/DEPLOY.md` 的 Nginx 範例，將 `/chat` 也用同樣方式轉發）。
diff --git a/web_client/index.html b/web_client/index.html
index 02ec57c..3cb085b 100644
--- a/web_client/index.html
+++ b/web_client/index.html
@@ -168,20 +168,20 @@
   </head>
   <body>
     <div class="wrap">
-      <h1>WD Gateway TTS Web Client Reference（WS API v1）</h1>
+      <h1>WD Orchestrator Web Client Reference（LLM → TTS, WS API v1）</h1>
       <div class="hint">
-        <div>此頁面只做最小可用與除錯，不追求 UI。訊息格式完全遵守 `docs/API.md` 的 WS API v1。</div>
+        <div>此頁面只做最小可用與除錯，不追求 UI。TTS 訊息格式完全遵守 `docs/API.md` 的 WS API v1。</div>
         <div>
-          Browser 原生 WebSocket 無法自訂 `Authorization` header；本工具會把 `API Key` 附加到 URL query
-         （例如 `?api_key=...`）。若你的 Gateway/Nginx 尚未支援此方式，請改由反向代理注入 header。
+          Browser 原生 WebSocket 無法自訂 `Authorization` header；本工具會把 `API Key` 附加到 URL query（例如
+          `?api_key=...`）。若你的部署要求 header 認證，請在 Nginx/Ingress 層注入。
         </div>
       </div>
 
       <div class="grid" style="margin-top: 14px">
         <div class="card">
           <div class="row">
-            <label>Gateway URL</label>
-            <input id="gatewayUrl" value="ws://localhost:9000/tts" />
+            <label>Orchestrator URL</label>
+            <input id="orchestratorUrl" value="ws://localhost:9100/chat" />
           </div>
           <div class="row">
             <label>API Key（可留空）</label>
@@ -203,6 +203,7 @@
               <label>sample_rate</label>
               <select id="sampleRate">
                 <option value="16000" selected>16000</option>
+                <option value="22050">22050</option>
                 <option value="24000">24000</option>
                 <option value="48000">48000</option>
               </select>
@@ -217,17 +218,11 @@
                 <option value="2">2</option>
               </select>
             </div>
-            <div class="row" style="grid-template-columns: 160px 1fr">
-              <label>text_delta 模式</label>
-              <select id="sendMode">
-                <option value="chunk" selected>逐段（一次送完整段）</option>
-                <option value="char">逐字（每字一個 text_delta）</option>
-              </select>
-            </div>
+            <div></div>
           </div>
 
           <div class="btns">
-            <button class="primary" id="btnConnect">Connect + Start</button>
+            <button class="primary" id="btnConnect">Connect</button>
             <button class="danger" id="btnDisconnect" disabled>Disconnect</button>
             <span class="pill" title="WebSocket 連線狀態">
               <span id="connDot" class="dot"></span>
@@ -236,21 +231,19 @@
           </div>
 
           <div class="row" style="grid-template-columns: 160px 1fr; margin-top: 14px">
-            <label>輸入文字</label>
-            <textarea id="inputText" placeholder="輸入文字後按 Send text_delta。"></textarea>
+            <label>輸入問題</label>
+            <textarea id="inputText" placeholder="輸入問題後按 Send prompt（會串流顯示文字，並同步產音播放）。"></textarea>
           </div>
 
           <div class="btns">
-            <button class="primary" id="btnSendDelta" disabled>Send text_delta</button>
-            <button id="btnTextEnd" disabled>Send text_end</button>
-            <button class="danger" id="btnCancel" disabled>Send cancel</button>
+            <button class="primary" id="btnSendPrompt" disabled>Send prompt</button>
+            <button class="danger" id="btnCancel" disabled>Cancel</button>
             <button id="btnClearLog">Clear log</button>
           </div>
 
           <div class="hint" style="margin-top: 10px">
             <div>
-              播放策略：使用 WebAudio 播放 `audio_chunk.audio_base64`（raw PCM16 little-endian）。`wav_header_base64`
-              僅用於除錯顯示/驗證格式。
+              播放策略：使用 WebAudio 播放 `audio_chunk.audio_base64`（raw PCM16 little-endian）。`wav_header_base64` 僅用於除錯顯示/驗證格式。
             </div>
             <div class="warn">注意：若 chunk 產生粒度較大或標點密度低，UnitLatency 可能出現長尾（屬正常現象）。</div>
           </div>
@@ -260,7 +253,7 @@
           <div class="kvs">
             <div class="k">session_id</div>
             <div id="dbgSessionId">-</div>
-            <div class="k">seq（client）</div>
+            <div class="k">seq（tts）</div>
             <div id="dbgSeq">-</div>
             <div class="k">TTFA</div>
             <div id="dbgTtfa">-</div>
@@ -278,6 +271,10 @@
               <div class="hint" style="margin-bottom: 6px">Last start_ack</div>
               <pre id="preStartAck">(none)</pre>
             </div>
+            <div>
+              <div class="hint" style="margin-bottom: 6px">LLM transcript</div>
+              <pre id="preLlm"></pre>
+            </div>
             <div>
               <div class="hint" style="margin-bottom: 6px">Event log</div>
               <pre id="preLog"></pre>
@@ -412,6 +409,13 @@
           this.started = true;
         }
 
+        async resume() {
+          if (!this.ctx) return;
+          if (this.ctx.state === "suspended") {
+            await this.ctx.resume();
+          }
+        }
+
         reset() {
           if (this.ctx) {
             try {
@@ -459,12 +463,12 @@
       const audioPlayer = new AudioPlayer();
 
       let ws = null;
-      let clientSeq = 1;
       let sessionId = randomUuidV4();
       let startSentAtMs = null;
       let ttfaMs = null;
       let chunksReceived = 0;
       let errorsReceived = 0;
+      let lastTtsSeq = null;
 
       function setConnState(state) {
         $("connText").textContent = state;
@@ -477,10 +481,9 @@
       function setUiConnected(connected) {
         $("btnConnect").disabled = connected;
         $("btnDisconnect").disabled = !connected;
-        $("btnSendDelta").disabled = !connected;
-        $("btnTextEnd").disabled = !connected;
+        $("btnSendPrompt").disabled = !connected;
         $("btnCancel").disabled = !connected;
-        $("gatewayUrl").disabled = connected;
+        $("orchestratorUrl").disabled = connected;
         $("apiKey").disabled = connected;
         $("sessionId").disabled = connected;
         $("audioFormat").disabled = connected;
@@ -490,7 +493,7 @@
 
       function updateDebug() {
         $("dbgSessionId").textContent = sessionId || "-";
-        $("dbgSeq").textContent = String(clientSeq);
+        $("dbgSeq").textContent = lastTtsSeq == null ? "-" : String(lastTtsSeq);
         $("dbgTtfa").textContent = ttfaMs == null ? "-" : `${ttfaMs.toFixed(0)} ms`;
         $("dbgChunks").textContent = String(chunksReceived);
         $("dbgErrors").textContent = String(errorsReceived);
@@ -502,35 +505,18 @@
         log("→ send", obj);
       }
 
-      function buildStartMessage() {
-        return {
-          type: "start",
-          session_id: sessionId,
-          audio_format: $("audioFormat").value,
-          sample_rate: Number($("sampleRate").value),
-          channels: Number($("channels").value),
-        };
-      }
-
-      function buildTextDelta(text) {
-        return { type: "text_delta", session_id: sessionId, seq: clientSeq++, text };
-      }
-
-      function buildTextEnd() {
-        return { type: "text_end", session_id: sessionId, seq: clientSeq++ };
-      }
-
       function buildCancel() {
-        return { type: "cancel", session_id: sessionId, seq: clientSeq++ };
+        return { type: "cancel" };
       }
 
       function resetSessionState() {
-        clientSeq = 1;
         startSentAtMs = null;
         ttfaMs = null;
         chunksReceived = 0;
         errorsReceived = 0;
+        lastTtsSeq = null;
         $("preStartAck").textContent = "(none)";
+        $("preLlm").textContent = "";
         updateDebug();
         audioPlayer.reset();
       }
@@ -550,8 +536,11 @@
         try {
           applySessionIdFromUi();
           resetSessionState();
+          // Autoplay policy: 建議在「使用者手勢」內建立並 resume AudioContext，避免後續 onmessage 才建立導致無聲。
+          audioPlayer.ensure(Number($("sampleRate").value));
+          await audioPlayer.resume();
 
-          const url = buildWsUrl($("gatewayUrl").value.trim(), $("apiKey").value.trim());
+          const url = buildWsUrl($("orchestratorUrl").value.trim(), $("apiKey").value.trim());
           ws = new WebSocket(url);
           setConnState("CONNECTING");
           setUiConnected(true);
@@ -559,12 +548,6 @@
 
           ws.onopen = () => {
             setConnState("CONNECTED");
-            try {
-              startSentAtMs = nowMs();
-              wsSend(buildStartMessage());
-            } catch (e) {
-              log(`start failed: ${String(e)}`);
-            }
             updateDebug();
           };
 
@@ -578,13 +561,33 @@
             }
             log("← recv", msg);
 
+            if (msg.type === "orchestrator_start") {
+              return;
+            }
+
+            if (msg.type === "llm_delta") {
+              $("preLlm").textContent += msg.delta || "";
+              return;
+            }
+
+            if (msg.type === "tool_calls_delta") {
+              return;
+            }
+
+            if (msg.type === "llm_done") {
+              return;
+            }
+
             if (msg.type === "start_ack") {
               $("preStartAck").textContent = safeJson(msg);
+              if (typeof msg.seq === "number") lastTtsSeq = msg.seq;
+              updateDebug();
               return;
             }
 
             if (msg.type === "audio_chunk") {
               chunksReceived++;
+              if (typeof msg.seq === "number") lastTtsSeq = msg.seq;
               $("dbgChunkSeq").textContent = String(msg.chunk_seq ?? "-");
               $("dbgUnitRange").textContent = `${msg.unit_index_start ?? "-"}..${msg.unit_index_end ?? "-"}`;
 
@@ -619,15 +622,27 @@
 
             if (msg.type === "tts_end") {
               log("tts_end received; server will close");
+              if (typeof msg.seq === "number") lastTtsSeq = msg.seq;
               updateDebug();
               return;
             }
 
             if (msg.type === "error") {
               errorsReceived++;
+              if (typeof msg.seq === "number") lastTtsSeq = msg.seq;
               updateDebug();
               return;
             }
+
+            if (msg.type === "orchestrator_error") {
+              errorsReceived++;
+              updateDebug();
+              return;
+            }
+
+            if (msg.type === "orchestrator_cancelled") {
+              return;
+            }
           };
 
           ws.onerror = () => {
@@ -654,31 +669,24 @@
         } catch {}
       });
 
-      $("btnSendDelta").addEventListener("click", async () => {
-        const text = $("inputText").value;
-        if (!text) return;
+      $("btnSendPrompt").addEventListener("click", async () => {
+        const prompt = $("inputText").value;
+        if (!prompt) return;
         try {
-          const mode = $("sendMode").value;
-          if (mode === "chunk") {
-            wsSend(buildTextDelta(text));
-          } else {
-            for (const ch of Array.from(text)) {
-              wsSend(buildTextDelta(ch));
-              await new Promise((r) => setTimeout(r, 0));
-            }
-          }
-          updateDebug();
-        } catch (e) {
-          log(`send text_delta failed: ${String(e)}`);
-        }
-      });
-
-      $("btnTextEnd").addEventListener("click", () => {
-        try {
-          wsSend(buildTextEnd());
+          resetSessionState();
+          audioPlayer.ensure(Number($("sampleRate").value));
+          await audioPlayer.resume();
+          startSentAtMs = nowMs();
+          wsSend({
+            prompt,
+            session_id: sessionId,
+            audio_format: $("audioFormat").value,
+            sample_rate: Number($("sampleRate").value),
+            channels: Number($("channels").value),
+          });
           updateDebug();
         } catch (e) {
-          log(`send text_end failed: ${String(e)}`);
+          log(`send prompt failed: ${String(e)}`);
         }
       });
 
