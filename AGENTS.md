# Repository Guidelines

## Project Structure & Module Organization
此倉庫目前以 SGLang 推論服務為主體，主要內容位於 `sglang-server/`。
- `docker-compose.yml`: 服務編排與資源設定（SGLang 推論服務）。
- `sglang-server/nginx/`: 反向代理與 SSL 設定。
- `sglang-server/monitoring/`: Prometheus 監控設定。
- `sglang-server/benchmark_final.py`: 核心壓力測試與資源監控腳本。
- `sglang-server/benchmark_report.md`: 壓測指標與效能回顧。
- Root README.md is the main doc; compose entry is docker-compose.yml.

## Build, Test, and Development Commands
- `cd sglang-server`：切到服務目錄。
- `cp .env.example .env`：建立環境變數檔。
- `docker compose up -d`：啟動推論服務（SGLang）。
- `docker compose logs -f sglang`：追蹤服務日誌。
- `python sglang-server/benchmark_final.py --concurrency 20 --total 50`：進行併發壓力測試。

## Coding Style & Naming Conventions
目前以 Python 為主：
- Python：依現有檔案使用 4 空白縮排、函式附簡短 docstring。
- 命名：採蛇形命名法 (snake_case)，變數與函式名稱需具描述性。

## Runtime & Deployment Notes
- 服務入口：預設對外埠 `8082`（容器內 `30000`）。
- 模型：`Qwen/Qwen2.5-1.5B-Instruct`。
- 特性：RadixAttention（系統提示快取、降低延遲）、Continuous Batching（高併發）。
- 環境：Windows（含 WSL2）或 Linux；需 NVIDIA GPU 與 Docker Desktop + NVIDIA Container Toolkit。

## Testing Guidelines
- 使用 `benchmark_final.py` 驗證推論引擎效能與工具調用 (Tool Use) 邏輯。
- 定期觀察 `benchmark_report.md` 中的指標是否回退。

## Commit & Pull Request Guidelines
根據歷史紀錄，提交訊息採 **Conventional Commits** 風格，例如：
- `feat: Add SGLang production server setup...`
- `refactor: Update benchmark script for improved monitoring`

## Security & Configuration Tips
- `.env` 不納入版控，務必設定 `SGLANG_API_KEY` 與 `HF_TOKEN`。
- HTTPS 憑證在 `sglang-server/nginx/certs/`，生產環境請替換為正式憑證。
