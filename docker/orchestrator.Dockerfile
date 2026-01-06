FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "aiohttp>=3.9.0,<4"

COPY orchestrator /app/orchestrator

EXPOSE 9100
CMD ["python", "-m", "orchestrator.server"]

