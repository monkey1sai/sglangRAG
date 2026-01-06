FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "aiohttp>=3.9.0,<4"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY sglang-server/ws_gateway_tts /app/ws_gateway_tts

EXPOSE 9000
CMD ["python", "-m", "ws_gateway_tts.container_entrypoint"]
