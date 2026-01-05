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
| `WS_TTS_ENGINE` | `dummy` | `dummy` / `piper` / `riva` |
| `RIVA_SERVER` | `localhost:50051` | 使用 `riva` engine 時的 gRPC 位址 |

### Piper（真實語音 / 開源可本地部署）

> Piper 需要你自行提供 piper CLI 與模型檔（.onnx）；本專案只提供 adapter。

| env var | 預設 | 說明 |
|---|---:|---|
| `PIPER_BIN` | (必填) | `piper` 可執行檔路徑 |
| `PIPER_MODEL` | (必填) | Piper 模型 `.onnx` 路徑 |
| `PIPER_SPEAKER_ID` | (空) | 多說話人模型用 |
| `PIPER_EXTRA_ARGS` | (空) | 直接追加到 piper CLI 的參數（進階） |
| `PIPER_OUTPUT_MODE` | `file` | `file`（較穩）或 `stdout`（若你的 piper 支援 `--output_file -`） |

建議（產品化）：
- `GATEWAY_API_KEY`（或 JWT 設定）用於 WS 認證
- per-tenant concurrency limit / rate limit 設定（視實作而定）

---

## 3. Docker Compose（最小形態）

> 說明：此 compose 目的在於「把 Gateway 服務化並固定 ports」，方便商業部署；SGLang 仍可使用既有 compose。

範例 `docker-compose.gateway.yml`（示意，可直接拷貝使用）：

```yaml
services:
  ws-gateway-tts:
    image: python:3.11-slim
    working_dir: /app/sglang-server
    volumes:
      - ./:/app
    environment:
      - WS_TTS_HOST=0.0.0.0
      - WS_TTS_PORT=9000
      - WS_TTS_ENGINE=dummy
      # - WS_TTS_ENGINE=riva
      # - RIVA_SERVER=riva:50051
    command: ["python", "-m", "ws_gateway_tts.server"]
    ports:
      - "9000:9000"
    restart: unless-stopped
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
