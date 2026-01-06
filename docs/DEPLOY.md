# WD 即時語音 AI Gateway — 部署指南（MVP）

本文件提供一個「可商業部署」的最小形態：TLS/反向代理、環境變數、ports、以及 docker-compose 範例。

---

## 1. Ports 與端點

### WD Gateway TTS

- WebSocket：`/tts`（對外）
- HTTP healthz：`/healthz`（對外或內部皆可）
- 預設 listen：`0.0.0.0:9000`

### SGLang Server

本專案 `sglang-server/docker-compose.yml` 預設對外：
- Host：`8082`
- Container：`30000`

---

## 2. 環境變數（WD Gateway TTS）

| env var | 預設 | 說明 |
|---|---:|---|
| `WS_TTS_HOST` | `0.0.0.0` | Gateway 綁定位址 |
| `WS_TTS_PORT` | `9000` | Gateway 對外 port |
| `WS_TTS_ENGINE` | `piper` | `dummy` / `piper` / `riva` |
| `RIVA_SERVER` | `localhost:50051` | 使用 `riva` engine 時的 gRPC 位址 |

### Piper（真實語音 / 開源可本地部署）

本專案預設採「named volume + 自動下載」：
- Piper binary / 模型 **不 bake 進 image**
- 第一次啟動容器會自動下載到 Docker named volume（例如 `/opt/piper`），之後重啟不會重複下載

| env var | 預設 | 說明 |
|---|---:|---|
| `PIPER_ROOT` | `/opt/piper` | Piper 下載/安裝根目錄（建議掛載到 named volume） |
| `PIPER_BIN` | `/opt/piper/piper` | Piper CLI 路徑 |
| `PIPER_MODEL` | `/opt/piper/models/zh_CN-huayan-medium.onnx` | 預設模型 |
| `PIPER_RELEASE_TAG` | 固定版本 | Piper release tag（固定，不用 latest） |
| `PIPER_TARBALL_URL` | 固定 URL | Piper tarball 下載網址 |
| `PIPER_TARBALL_SHA256` | 固定 SHA256 | tarball 校驗 |
| `PIPER_MODEL_ONNX_URL` | 固定 URL | 預設模型下載網址 |
| `PIPER_MODEL_ONNX_SHA256` | 固定 SHA256 | 模型校驗 |
| `PIPER_MODEL_JSON_URL` | 固定 URL | `.onnx.json` 下載網址 |
| `PIPER_MODEL_JSON_SHA256` | 固定 SHA256 | `.onnx.json` 校驗 |
| `PIPER_SPEAKER_ID` | (空) | 多說話人模型用 |
| `PIPER_EXTRA_ARGS` | (空) | 直接追加到 piper CLI 的參數（進階） |
| `PIPER_OUTPUT_MODE` | `file` | `file`（較穩）或 `stdout`（若你的 piper 支援 `--output_file -`） |

建議（產品化）：
- `GATEWAY_API_KEY`（或 JWT 設定）用於 WS 認證
- per-tenant concurrency limit / rate limit 設定（視實作而定）

---

## 3. Docker Compose（最小形態）

> 建議直接使用本 repo 的 `sglang-server/docker-compose.yml`（已包含 named volume + 自動下載 Piper）。

若你只想單獨部署 ws_gateway_tts，可參考以下示意（重點：named volume 掛載到 `/opt/piper`）：

```yaml
services:
  ws-gateway-tts:
    image: python:3.11-slim
    environment:
      - WS_TTS_HOST=0.0.0.0
      - WS_TTS_PORT=9000
      - WS_TTS_ENGINE=piper
      - PIPER_ROOT=/opt/piper
      - PIPER_BIN=/opt/piper/piper
      - PIPER_MODEL=/opt/piper/models/zh_CN-huayan-medium.onnx
      # 其餘固定版本 URL/SHA256 請參考 repo 的 compose
    volumes:
      - piper-data:/opt/piper
    ports:
      - "9000:9000"
    restart: unless-stopped

volumes:
  piper-data:
```

啟動：

```powershell
docker compose -f docker-compose.gateway.yml up -d
```

健康檢查：

```powershell
curl http://localhost:9000/healthz
```

---

## 4. Nginx（WS upgrade）範例

將 Gateway 對外域名設為 `wss://<host>/tts` 的典型設定：

```nginx
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

upstream ws_gateway_tts {
  server 127.0.0.1:9000;
}

server {
  listen 443 ssl http2;
  server_name _;

  # ssl_certificate /etc/nginx/certs/cert.pem;
  # ssl_certificate_key /etc/nginx/certs/key.pem;

  location /healthz {
    proxy_pass http://ws_gateway_tts/healthz;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
  }

  location /tts {
    proxy_pass http://ws_gateway_tts/tts;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WS 長連線，避免過早超時
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
  }
}
```

---

## 5. 最小驗收 Checklist（部署）

- `curl http://localhost:9000/healthz` 回 `{"status":"ok", ...}`
- Browser/benchmark 可連上 `ws://localhost:9000/tts`
- Nginx 轉發後可連上 `wss://<host>/tts`（WS upgrade 正常）
- 服務重啟後可自動恢復（`restart: unless-stopped` 或 systemd）
