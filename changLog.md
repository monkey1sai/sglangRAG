## change prompt v 0.1.0 
你現在在一個 repo：sglang-server/。目前 README 的流程是：
- Step 1 用 docker compose up -d 啟動 SGLang（Docker）
- Step 2 手動在本機 venv 啟動 ws_gateway_tts.server（先用 DummyTtsEngine）
- Step 3 再啟動 Orchestrator（目前也是分步驟手動啟動）

我希望調整成：在執行「Step 1: docker compose up -d」的同時，就把以下兩個也一起啟動完成：
1) ws_gateway_tts（先用 dummy engine）
2) Orchestrator

並且要讓 client 可以用「IP + SGLANG_API_KEY」直接連到 SGLang 進行對話（外部機器連線），而不是只能 localhost。

請你完成以下修改（不要只寫建議，要直接改檔）：

【目標與驗收條件】
A. 一條指令即可啟動全部：在 sglang-server/ 目錄執行 `docker compose up -d` 後：
   - SGLang API 可從外部機器用 http://<HOST_IP>:<PORT>/ 存取（或經 Nginx reverse proxy 的同等路徑）
   - client request 必須帶 SGLANG_API_KEY 才能對話（維持原本的 key 機制）
   - ws_gateway_tts 以 dummy 模式啟動，且健康檢查 http://<HOST_IP>:9000/healthz 可通
   - Orchestrator 服務也在 compose 內啟動完成，並有健康檢查 endpoint（如果原本沒有就加一個簡單的 /healthz）

B. README 要更新：把 Step 2/3 的手動啟動方式改成「compose 已自動啟動」，仍保留進階說明（例如 piper 模式怎麼切換）。

【你需要做的事情】
1. 修改 `sglang-server/docker-compose.yml`
   - 新增 service: `ws_gateway_tts`，用 repo 內的程式啟動 `python -m ws_gateway_tts.server`
   - 預設環境變數：WS_TTS_ENGINE=dummy, WS_TTS_PORT=9000
   - 對外 publish port 9000:9000
   - 加上 healthcheck（curl http://localhost:9000/healthz）
   - 設定 restart: unless-stopped

2. 新增或修改 Dockerfile（如果 repo 已有可重用的 python image 就沿用；沒有就新增）
   - 確保 ws_gateway_tts service 內有 python runtime、能安裝相依（requirements/pyproject 擇一）
   - 不要依賴本機 venv

3. 新增 service: `orchestrator`
   - 以容器方式啟動（同上：有現成啟動命令就用，沒有就新增 minimal 可啟動的 entrypoint）
   - 對外 publish 一個 port（請選一個合理且不衝突的，例如 9100 或 8001）
   - 提供 /healthz（若原本 orchestrator 程式沒有，請加最小改動提供健康檢查）

4. 讓「client 用 IP + api key 對話」成立
   - 確保 SGLang/NGINX 的 listen 綁定在 0.0.0.0，不是 127.0.0.1
   - docker compose 需要 publish 對外可連線的 port（若已有 nginx 反代，請確認 nginx 也 publish）
   - README 補上一段「遠端 client 連線範例」：
     - 以 curl 示範呼叫（包含 header 或 query 的 api key，依你專案原本驗證方式）
     - 提醒使用者在 .env 設定 SGLANG_API_KEY

5) 將 web_client 也納入 docker compose：
- 以 nginx（或等效靜態 server）提供 web_client 靜態檔案
- 讓外部可用 http://<HOST_IP>/ 直接開前端
- 前端呼叫後端一律走同網域路徑（例如 /api 反代到 SGLang，/tts 反代到 ws_gateway_tts），避免 CORS
- README 更新：移除手動 python -m http.server 8000 為預設步驟，但保留 dev 模式說明

【約束】
- 預設仍用 dummy TTS（會是嘟聲），但保留切換到 piper 的 env 範例（README）
- 不要破壞原本的 benchmark_final.py 壓測流程
- 變更後所有服務都應該在 `docker compose ps` 看到 running/healthy（若支援 healthcheck）

完成後請輸出：
- 你改了哪些檔案（含路徑）
- 變更內容摘要
- 我該怎麼跑（從乾淨環境開始的一組指令）

## change prompt v 0.1.1
目前 ws_gateway_tts 在 Docker 裡仍可能回到 DummyTtsEngine（嘟嘟聲）。
我已確認原因之一是 Piper 的部署方式不符合「一鍵部署、跨環境可重複」的要求。

我的最終需求是：未來在任何全新環境（乾淨機器，沒有任何事前準備）
只要執行：
  docker compose up -d --build
即可讓 web client 真正用 Piper TTS 發聲（不是 dummy），
且 Docker image 本身不會因為內含模型而變得很胖。

【核心設計原則（請嚴格遵守）】
- Piper binary + 模型「不要 bake 進 image」
- 不使用 host bind mount（不要要求使用者自己準備 piper/ 目錄）
- 使用 Docker named volume，在 container 第一次啟動時自動下載
- 之後重啟 container 不會重複下載（volume 持久化）

【硬性驗收條件】
A) 預設情況下（不改 .env），ws_gateway_tts 必須啟用 Piper：
   - curl http://localhost:9000/healthz 內的 engine_resolved = "piper"
   - web client 播放 TTS 為正常語音（非嘟嘟聲）

B) 新環境 zero manual steps：
   - 使用者不需要下載 piper
   - 不需要準備模型 .onnx
   - 不需要 chmod / mkdir
   - 不需要改 compose 才能出聲音

C) Docker image size 控制合理：
   - Piper binary / model 不放進 image layer
   - 使用 named volume 儲存（例如 /opt/piper）

【你要實作的方式（請直接改檔落地）】

1) docker-compose.yml
   - 為 ws_gateway_tts 新增 named volume（例如 piper-data）
   - 將 volume 掛載到容器內固定路徑（例如 /opt/piper）
   - 預設 env：
       WS_TTS_ENGINE=piper
       PIPER_BIN=/opt/piper/piper
       PIPER_MODEL=/opt/piper/models/<default>.onnx

2) ws_gateway_tts 容器啟動流程
   - 在 container entrypoint 或 startup script 中：
     - 若 /opt/piper/piper 不存在 → 自動下載「Linux 版」piper binary（固定版本）
     - 若模型不存在 → 自動下載預設模型到 /opt/piper/models/
     - 下載完成後再啟動 ws_gateway_tts.server
   - 下載來源請使用固定版本與可驗證來源（非 latest）
   - 若下載失敗，容器啟動應失敗並明確 log 原因（不要 silent fallback 到 dummy）

3) healthz 強化
   - /healthz 回傳內容至少包含：
       engine_resolved
       piper_binary_exists (true/false)
       piper_model_exists (true/false)
       model_sample_rate（如果可取得）
   - 這是驗收 Piper 是否真的可用的依據

4) README / .env.example 更新
   - 明確說明：
     - 預設使用 Piper（named volume 自動下載）
     - 第一次啟動會花時間下載（正常現象）
     - 如何切回 dummy（WS_TTS_ENGINE=dummy）
     - 如何更換 Piper 模型（清空 volume 或改 env）

5) 相容性注意事項
   - Piper 模型若為 22050Hz，請在 README 清楚標註
   - 若你能讓 gateway 對外回報 sample_rate 供前端使用，請一併完成

【交付內容】
- 列出你修改/新增的檔案（含路徑）
- 提供完整 diff 或完整檔案內容（至少 docker-compose.yml、Dockerfile/entrypoint、README 相關段落）
- 提供一組「從乾淨環境開始」的驗收指令：
   - docker compose up -d --build
   - curl http://localhost:9000/healthz
   - web client 播放測試方式

## change prompt v 0.1.2
你現在在 repo 根目錄。請把目前 named volume 版的 Piper 一鍵部署整理到可直接合併上主分支的品質，最後完成 git push。

【目標】
- 確保 `docker compose up -d --build` 能啟動：sglang / ws_gateway_tts(Piper default) / orchestrator / web (nginx)
- ws_gateway_tts 預設使用 Piper 且採 named volume 自動下載，不依賴 host bind mount
- README/.env.example/docker-compose.yml 與實作一致（避免文件說一套、程式跑一套）
- 乾淨可讀的 git diff：刪除多餘檔案、統一命名、避免硬編路徑、避免重複設定

【你要做的事情（按順序）】

1) 先做 repo health check
   - `git status` 確認有哪些變更
   - `docker compose config` 確認 compose 語法正確
   - `docker compose up -d --build` 跑一次（若你無法實際跑，至少確保設定邏輯正確）
   - 確認 healthcheck endpoint 在 README 中存在且對得上（9000/9100/8082/8080）
   - 確認 named volume 存在於 compose 中（例如 piper-data），並掛載到 /opt/piper

2) 程式碼與設定整理（不要改動功能，主要是清理與一致性）
   - 統一 ws_gateway_tts 的啟動入口：
     - 建議用 entrypoint.sh 或 python module wrapper，負責「首次下載 piper + model 到 /opt/piper」與 checksum 驗證
     - 下載來源必須固定版本 + sha256（不要 latest）
     - 下載失敗要 fail loud（容器退出並輸出 log），不要 fallback dummy
   - docker-compose.yml：
     - 整理 env 來源（優先用 .env / .env.example），避免重複宣告
     - 確保 web/nginx 反代路徑一致：/api /tts /chat
     - 確保 ports 對外可連（0.0.0.0 listen）
   - README/.env.example：
     - 把「一鍵部署」「第一次會下載」「如何切 dummy」「如何清 volume」說清楚
     - 遠端 client 直連 SGLang 的 curl 範例保持可用（Authorization: Bearer）
   - 清理：移除未使用的檔案/註解/重複文件段落（但不要刪掉必要的 dev mode 說明）

3) 自動格式化/靜態檢查（能做就做）
   - 如果有 python 格式化工具（ruff/black/isort）就執行；沒有就保持變更最小但確保風格一致
   - 若有 shell script，確保可執行、並用 LF line endings

4) 準備 commit（分兩種都可以，但請不要太碎）
   - 建議 commit message：
     "feat: one-command deploy with Piper TTS via named volume"
   - commit 內容應包含：
     - ws_gateway_tts: named volume auto-download piper+model, healthz enrich
     - compose: add piper-data volume + wiring
     - docs: update README/.env.example to match

5) 推送到遠端
   - 先 `git remote -v` 找出預設遠端（通常 origin）
   - 先確認目前分支（git branch --show-current）
   - push：
     - 若是 main/master：直接 push
     - 若不是：push 到同名分支，並輸出下一步如何開 PR

【交付給我看的輸出】
- (A) `git status`（push 前）
- (B) `git diff --stat`
- (C) 最終 commit hash + commit message
- (D) `git push` 的結果（成功訊息）
- (E) 一段最短的驗收指令（3~6 行）：
     docker compose up -d --build
     curl http://localhost:9000/healthz
     curl http://localhost:9100/healthz
     curl -i http://localhost:8082/health
     # 打開 http://localhost:8080/ 測 web

【重要約束】
- 不要引入需要使用者手動準備檔案的步驟（禁止 ../piper bind mount）
- 下載與 checksum 失敗要明確報錯，不可默默切 dummy
- 不要破壞 benchmark_final.py、ws_tts_benchmark.py 等現有測試腳本（文件可補充但功能不能壞）


----

### changeLog V 0.1.3

請幫我做一次「安全的檔案搬移 + README 入口整理」，目標是把 docker-compose.yml 與 README.md
移到 repo root，但【服務邏輯完全不變】。

⚠️ 這次重構只允許「因路徑改變而必要的修正」，禁止任何架構或行為改動。

【我要的結果】
1) `sglang-server/docker-compose.yml` → 移到 repo root 成為 `./docker-compose.yml`
2) `sglang-server/README.md` → 移到 repo root 成為 `./README.md`
3) README 整理成「repo root 的入口文件」，提供清楚的一鍵啟動方式：
   - `docker compose up -d --build`
4) compose 的服務、port、healthcheck、named volume（Piper）行為全部維持不變

---

## 🔒 三個「必須特別小心、不可改壞」的關鍵點（請嚴格遵守）

### (1) build.context / dockerfile 路徑
- docker-compose.yml 移到 repo root 後：
  - **所有 build.context 必須明確指向 sglang-server 子目錄**
  - **dockerfile 路徑要能正確找到原本的 Dockerfile**
- ❌ 不可把 Dockerfile 搬位置
- ❌ 不可改 build target / args
- ✅ 只修正「相對路徑基準從 sglang-server → repo root」

👉 這是最容易讓 compose build 失敗的地方，請逐一確認。

---

### (2) volumes（尤其 nginx / web / piper named volume）
- named volume（例如 piper-data）：
  - 行為完全不變（仍然 auto-download Piper 到 volume）
  - 只允許修正掛載來源的相對路徑（若有）
- nginx / web 的 volumes：
  - 若原本是 `./nginx`，現在應改成 `./sglang-server/nginx`
  - 若原本是 `./web_client`，請依實際結構修正
- ❌ 不可把 named volume 改成 bind mount
- ❌ 不可新增/刪除 volume

👉 這一點若改錯，會導致 nginx 起來但沒內容、或 Piper 失效。

---

### (3) env_file / .env / README 指令一致性
- docker-compose.yml 中：
  - 若有 `env_file: .env`，請確認是 **以 repo root 為基準**
  - 若原本是 `sglang-server/.env`，請只修正路徑，不改變使用方式
- README：
  - 所有指令一律以「repo root」為執行目錄
  - 不要再把 `cd sglang-server` 當成主要流程
  - 若需要 dev / advanced 用法，可在後段說明

👉 README 與 compose 若不一致，會造成「照文件跑卻起不來」的問題。

---

## 🛠 你要做的事情（流程）

A) 檔案搬移
- 移動 docker-compose.yml 到 repo root
- 移動 README.md 到 repo root
- 若 repo root 原已有 README，請整合為單一入口版（避免雙 README）

B) docker-compose.yml 路徑修正（僅限以下類型）
- build.context / dockerfile
- volumes（路徑來源）
- env_file
- 其他欄位（ports、env、command、depends_on、healthcheck、restart）不得改

C) README 重整（內容不刪，只重排與精煉）
README 請至少包含：
1. Quick Start（一鍵啟動）
2. 第一次啟動會下載 Piper（named volume）
3. 服務與 port 一覽
4. healthz 驗收指令
5. 遠端 client 直連 SGLang（Bearer API key）
6. 進階：切 dummy / 清 volume / sample_rate 提醒

---

## ✅ 最終自我檢查（請在輸出中回報）
- `docker compose config` 可以成功（代表路徑正確）
- README 內所有指令都能在 repo root 執行
- named volume 行為與原本一致（非 bind mount）
- 列出你實際修改的檔案與「修正了哪些路徑」

【輸出格式】
1) 檔案搬移清單
2) docker-compose.yml 的路徑修正摘要（逐項列出）
3) 更新後 README 的「Quick Start + 驗收」完整內容
