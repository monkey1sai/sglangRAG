from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from aiohttp import WSMsgType, web

from .protocol import (
    CancelMessage,
    ResumeMessage,
    StartMessage,
    TextDeltaMessage,
    TextEndMessage,
)
from .session import SessionManager
from .tts_engines.base import AudioSpec
from .tts_engines.dummy import DummyTtsEngine
from .tts_engines.piper import PiperTtsEngine
from .tts_engines.riva import RivaTtsEngine


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


async def send_json(ws: web.WebSocketResponse, payload: Dict[str, Any]) -> None:
    await ws.send_str(json_dumps(payload))


def _prom_escape_label_value(value: str) -> str:
    # Prometheus exposition format string escaping (minimal set we need).
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _fmt_prom_line(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> str:
    if labels:
        labels_str = ",".join(f'{k}="{_prom_escape_label_value(str(v))}"' for k, v in sorted(labels.items()))
        return f"{name}{{{labels_str}}} {value}"
    return f"{name} {value}"


def _percentiles(values: Deque[float]) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    xs = sorted(values)

    def pick(p: float) -> float:
        if p <= 0:
            return xs[0]
        if p >= 100:
            return xs[-1]
        idx = (len(xs) - 1) * (p / 100.0)
        lo = int(idx)
        hi = min(lo + 1, len(xs) - 1)
        frac = idx - lo
        return xs[lo] * (1 - frac) + xs[hi] * frac

    return pick(50), pick(95), pick(99)


class Metrics:
    def __init__(self) -> None:
        self.active_connections = 0
        self.sessions_total = 0
        self.backpressure_total = 0
        self.errors_total_by_code: Dict[str, int] = {}
        self._ttfa_ms: Deque[float] = deque(maxlen=5000)
        self._lock = asyncio.Lock()

    async def inc_active(self, delta: int) -> None:
        async with self._lock:
            self.active_connections += delta

    async def inc_sessions(self) -> None:
        async with self._lock:
            self.sessions_total += 1

    async def inc_error(self, code: str) -> None:
        async with self._lock:
            self.errors_total_by_code[code] = self.errors_total_by_code.get(code, 0) + 1
            if code == "backpressure":
                self.backpressure_total += 1

    async def observe_ttfa_ms(self, ttfa_ms: float) -> None:
        async with self._lock:
            self._ttfa_ms.append(float(ttfa_ms))

    async def render_prometheus(self) -> str:
        async with self._lock:
            active = self.active_connections
            sessions_total = self.sessions_total
            backpressure_total = self.backpressure_total
            errors_by_code = dict(self.errors_total_by_code)
            ttfa_values = deque(self._ttfa_ms)

        p50, p95, p99 = _percentiles(ttfa_values)
        ttfa_sum = float(sum(ttfa_values)) if ttfa_values else 0.0
        ttfa_count = float(len(ttfa_values))

        lines = []
        lines.append("# HELP ws_gateway_active_connections Active WebSocket connections.")
        lines.append("# TYPE ws_gateway_active_connections gauge")
        lines.append(_fmt_prom_line("ws_gateway_active_connections", float(active)))

        lines.append("# HELP ws_gateway_sessions_total Total sessions started (start messages accepted).")
        lines.append("# TYPE ws_gateway_sessions_total counter")
        lines.append(_fmt_prom_line("ws_gateway_sessions_total", float(sessions_total)))

        lines.append("# HELP ws_gateway_errors_total Total errors by code.")
        lines.append("# TYPE ws_gateway_errors_total counter")
        for code, count in sorted(errors_by_code.items()):
            lines.append(_fmt_prom_line("ws_gateway_errors_total", float(count), {"code": code}))

        lines.append("# HELP ws_gateway_backpressure_total Total backpressure errors.")
        lines.append("# TYPE ws_gateway_backpressure_total counter")
        lines.append(_fmt_prom_line("ws_gateway_backpressure_total", float(backpressure_total)))

        lines.append("# HELP ws_gateway_ttfa_ms Time-to-first-audio in milliseconds (summary over recent samples).")
        lines.append("# TYPE ws_gateway_ttfa_ms summary")
        lines.append(_fmt_prom_line("ws_gateway_ttfa_ms", p50, {"quantile": "0.5"}))
        lines.append(_fmt_prom_line("ws_gateway_ttfa_ms", p95, {"quantile": "0.95"}))
        lines.append(_fmt_prom_line("ws_gateway_ttfa_ms", p99, {"quantile": "0.99"}))
        lines.append(_fmt_prom_line("ws_gateway_ttfa_ms_sum", ttfa_sum))
        lines.append(_fmt_prom_line("ws_gateway_ttfa_ms_count", ttfa_count))

        return "\n".join(lines) + "\n"


def build_wav_header(*, sample_rate: int, channels: int) -> bytes:
    """
    產生 PCM16 (s16le) 的 WAV header（44 bytes）。
    注意：WAV header 需要 data size；此處以 0 填入，client 若要存檔可自行修正。
    """
    bits_per_sample = 16
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)

    def u32(x: int) -> bytes:
        return int(x).to_bytes(4, "little", signed=False)

    def u16(x: int) -> bytes:
        return int(x).to_bytes(2, "little", signed=False)

    # RIFF chunk size = 36 + data size; data size unknown -> 0
    riff_size = 36
    data_size = 0
    return b"".join(
        [
            b"RIFF",
            u32(riff_size),
            b"WAVE",
            b"fmt ",
            u32(16),  # PCM fmt chunk size
            u16(1),  # PCM format
            u16(channels),
            u32(sample_rate),
            u32(byte_rate),
            u16(block_align),
            u16(bits_per_sample),
            b"data",
            u32(data_size),
        ]
    )


def build_engine() -> Any:
    engine_name = os.getenv("WS_TTS_ENGINE", "piper").lower().strip()
    if engine_name == "dummy":
        return engine_name, DummyTtsEngine()
    if engine_name == "piper":
        return engine_name, PiperTtsEngine.from_env()
    if engine_name == "riva":
        server = os.getenv("RIVA_SERVER", "localhost:50051")
        return engine_name, RivaTtsEngine(server=server)
    raise ValueError(f"未知 WS_TTS_ENGINE: {engine_name}")


class GatewayApp:
    def __init__(self) -> None:
        self.started_at_utc = dt.datetime.now(dt.timezone.utc)
        self.engine_name, self.engine = build_engine()
        self.sessions = SessionManager(self.engine)
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self.metrics = Metrics()

    async def on_startup(self, app: web.Application) -> None:
        self._cleanup_task = asyncio.create_task(self.sessions.cleanup_loop())

    async def on_cleanup(self, app: web.Application) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except Exception:
                pass

    async def healthz(self, request: web.Request) -> web.Response:
        now = dt.datetime.now(dt.timezone.utc)
        uptime_s = (now - self.started_at_utc).total_seconds()
        from .piper_bootstrap import get_piper_health_fields

        piper_fields = get_piper_health_fields()
        return web.json_response(
            {
                "status": "ok",
                "engine": os.getenv("WS_TTS_ENGINE", "piper"),
                "engine_resolved": self.engine_name,
                "version": os.getenv("WS_TTS_VERSION", "dev"),
                "started_at": self.started_at_utc.isoformat(),
                "uptime_s": uptime_s,
                **piper_fields,
            }
        )

    async def metrics_endpoint(self, request: web.Request) -> web.Response:
        payload = await self.metrics.render_prometheus()
        return web.Response(text=payload, content_type="text/plain; version=0.0.4")

    async def ws_tts(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        send_lock = asyncio.Lock()
        state = None
        sender_task: Optional[asyncio.Task[None]] = None
        start_monotonic_s: Optional[float] = None
        ttfa_recorded = False

        await self.metrics.inc_active(+1)

        async def send_json_locked(payload: Dict[str, Any]) -> None:
            async with send_lock:
                await send_json(ws, payload)

        async def sender_loop() -> None:
            assert state is not None
            while not ws.closed:
                msg = await state.send_queue.get()
                try:
                    nonlocal ttfa_recorded
                    if not ttfa_recorded and msg.get("type") == "audio_chunk" and start_monotonic_s is not None:
                        ttfa_recorded = True
                        ttfa_ms = (time.monotonic() - start_monotonic_s) * 1000.0
                        await self.metrics.observe_ttfa_ms(ttfa_ms)
                    if msg.get("type") == "error":
                        code = msg.get("code")
                        if isinstance(code, str) and code:
                            await self.metrics.inc_error(code)
                    await send_json_locked(msg)
                except Exception:
                    await ws.close()
                    break
                if msg.get("type") in ("tts_end", "error"):
                    await ws.close()
                    break

        async def fail(code: str, message: str, *, seq: Optional[int] = None) -> None:
            nonlocal state
            await self.metrics.inc_error(code)
            payload = {
                "type": "error",
                "session_id": state.session_id if state else "",
                "seq": seq if seq is not None else (state.seq if state else 0),
                "code": code,
                "message": message,
            }
            try:
                await send_json_locked(payload)
            finally:
                await ws.close()

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue

                try:
                    obj = json.loads(msg.data)
                    if not isinstance(obj, dict):
                        raise ValueError("JSON 必須是物件")
                except Exception as e:
                    await fail("bad_request", f"JSON 解析失敗: {e}")
                    break

                msg_type = obj.get("type")
                if not isinstance(msg_type, str):
                    await fail("bad_request", "缺少 type 欄位")
                    break

                if msg_type == "start":
                    start = StartMessage.parse(obj)
                    audio_spec = AudioSpec(
                        audio_format=start.audio_format,
                        sample_rate=start.sample_rate,
                        channels=start.channels,
                    )
                    state = await self.sessions.get_or_create(start.session_id, audio_spec)
                    state.touch()
                    start_monotonic_s = time.monotonic()
                    await self.metrics.inc_sessions()

                    if sender_task is None or sender_task.done():
                        sender_task = asyncio.create_task(sender_loop())

                    start_ack: Dict[str, Any] = {
                        "type": "start_ack",
                        "session_id": state.session_id,
                        "audio_format": state.audio_spec.audio_format,
                        "sample_rate": state.audio_spec.sample_rate,
                        "channels": state.audio_spec.channels,
                        "ttl_s": state.ttl_s,
                    }
                    # 若 client 指定 pcm16_wav：audio_chunk 仍傳 raw PCM16，並提供 wav header 方便 client 組檔/播放。
                    if state.audio_spec.audio_format == "pcm16_wav":
                        hdr = build_wav_header(
                            sample_rate=state.audio_spec.sample_rate,
                            channels=state.audio_spec.channels,
                        )
                        start_ack["wav_header_base64"] = base64.b64encode(hdr).decode("ascii")

                    await send_json_locked(start_ack)
                    continue

                if state is None:
                    await fail("bad_request", "請先送 start")
                    break

                state.touch()

                if msg_type == "text_delta":
                    delta = TextDeltaMessage.parse(obj)
                    if delta.session_id != state.session_id:
                        await fail("bad_request", "session_id 不一致", seq=delta.seq)
                        break
                    state.seq = delta.seq
                    state.enqueue_text_units(delta.text)
                    await self.sessions.start_synth_loop_if_needed(state)
                    continue

                if msg_type == "text_end":
                    end = TextEndMessage.parse(obj)
                    if end.session_id != state.session_id:
                        await fail("bad_request", "session_id 不一致", seq=end.seq)
                        break
                    state.seq = end.seq
                    state.finished = True
                    await self.sessions.start_synth_loop_if_needed(state)
                    # tts_end 會由 synth loop 放入 send_queue，sender_loop 送出後自動關閉連線。
                    continue

                if msg_type == "cancel":
                    cancel = CancelMessage.parse(obj)
                    state.seq = cancel.seq
                    await self.sessions.cancel(state)
                    await state.send_queue.put(
                        {"type": "tts_end", "session_id": state.session_id, "seq": state.seq, "cancelled": True}
                    )
                    continue

                if msg_type == "resume":
                    resume = ResumeMessage.parse(obj)
                    if resume.session_id != state.session_id:
                        await fail("bad_request", "session_id 不一致")
                        break
                    last = resume.last_unit_index_received
                    resent = 0
                    for chunk in state.cache:
                        if chunk.unit_index_end <= last:
                            continue
                        await send_json_locked(chunk.to_ws_message(session_id=state.session_id, seq=state.seq))
                        resent += 1
                    if resent == 0:
                        await send_json_locked(
                            {
                                "type": "error",
                                "session_id": state.session_id,
                                "seq": state.seq,
                                "code": "resume_not_available",
                                "message": "快取窗外或無可續傳內容，請重新開始",
                            },
                        )
                    continue

                await fail("bad_request", f"未知 type: {msg_type}")
                break
        except Exception as e:
            try:
                await fail("internal_error", str(e))
            except Exception:
                pass
        finally:
            if sender_task:
                sender_task.cancel()
                try:
                    await sender_task
                except Exception:
                    pass
            await self.metrics.inc_active(-1)
            await ws.close()

        return ws


def create_app() -> web.Application:
    gateway = GatewayApp()
    app = web.Application()
    app.on_startup.append(gateway.on_startup)
    app.on_cleanup.append(gateway.on_cleanup)
    app.router.add_get("/healthz", gateway.healthz)
    app.router.add_get("/metrics", gateway.metrics_endpoint)
    app.router.add_get("/tts", gateway.ws_tts)
    return app


def main() -> None:
    host = os.getenv("WS_TTS_HOST", "0.0.0.0")
    port = int(os.getenv("WS_TTS_PORT", "9000"))
    app = create_app()
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
