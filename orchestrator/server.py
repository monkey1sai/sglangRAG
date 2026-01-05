from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import WSMsgType, web


PUNCTUATION = set("，。！？；：,.!?;\n")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


async def ws_send_json(ws: web.WebSocketResponse, payload: Dict[str, Any]) -> None:
    await ws.send_str(json_dumps(payload))


def _require_str(obj: Dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str) or not val:
        raise ValueError(f"欄位 {key} 必須是非空字串")
    return val


def _require_int(obj: Dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if not isinstance(val, int):
        raise ValueError(f"欄位 {key} 必須是整數")
    return val


def _optional_str(obj: Dict[str, Any], key: str) -> Optional[str]:
    val = obj.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ValueError(f"欄位 {key} 必須是字串")
    return val


@dataclass(frozen=True)
class ChatRequest:
    prompt: str
    session_id: str
    audio_format: str
    sample_rate: int
    channels: int
    # Optional: for local debugging only (disabled by default)
    ws_tts_url: Optional[str] = None

    @staticmethod
    def parse(obj: Dict[str, Any]) -> "ChatRequest":
        return ChatRequest(
            prompt=_require_str(obj, "prompt"),
            session_id=_require_str(obj, "session_id"),
            audio_format=_require_str(obj, "audio_format"),
            sample_rate=_require_int(obj, "sample_rate"),
            channels=_require_int(obj, "channels"),
            ws_tts_url=_optional_str(obj, "ws_tts_url"),
        )


@dataclass
class ToolCallAccum:
    index: int
    tool_call_id: str = ""
    function_name: str = ""
    arguments: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "id": self.tool_call_id,
            "function": {"name": self.function_name, "arguments": self.arguments},
        }


def _apply_tool_calls_delta(acc: Dict[int, ToolCallAccum], tool_calls: List[Dict[str, Any]]) -> None:
    for i, tc in enumerate(tool_calls):
        idx = tc.get("index")
        if not isinstance(idx, int):
            idx = i
        cur = acc.get(idx)
        if cur is None:
            cur = ToolCallAccum(index=idx)
            acc[idx] = cur

        tc_id = tc.get("id")
        if isinstance(tc_id, str) and tc_id:
            cur.tool_call_id = tc_id

        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = fn.get("name")
        if isinstance(name, str) and name:
            cur.function_name = name

        args = fn.get("arguments")
        if isinstance(args, str) and args:
            cur.arguments += args


def _build_sglang_url() -> str:
    base = os.getenv("SGLANG_BASE_URL", "http://localhost:8082").rstrip("/")
    return f"{base}/v1/chat/completions"


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


async def _stream_sglang_deltas(
    *,
    client: aiohttp.ClientSession,
    prompt: str,
    ws: web.WebSocketResponse,
    tts_text_queue: "asyncio.Queue[Optional[str]]",
    tts_flush_min_chars: int,
    tts_flush_on_punct: bool,
    stop: asyncio.Event,
) -> Dict[str, Any]:
    sglang_url = _build_sglang_url()
    api_key = os.getenv("SGLANG_API_KEY", "")
    model = os.getenv("SGLANG_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

    if not api_key:
        raise RuntimeError("缺少環境變數 SGLANG_API_KEY")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }

    headers = {"Authorization": f"Bearer {api_key}"}
    tool_acc: Dict[int, ToolCallAccum] = {}
    full_text = ""
    tts_buffer = ""

    async with client.post(sglang_url, json=payload, headers=headers) as resp:
        if resp.status != 200:
            body = (await resp.text())[:2000]
            raise RuntimeError(f"SGLang 回應 {resp.status}: {body}")

        while not stop.is_set():
            line = await resp.content.readline()
            if not line:
                break
            s = line.decode("utf-8", errors="replace").strip()
            if not s.startswith("data: "):
                continue
            if s == "data: [DONE]":
                break

            try:
                delta = json.loads(s[6:])["choices"][0]["delta"]
            except Exception:
                await ws_send_json(ws, {"type": "orchestrator_error", "code": "llm_parse_error", "message": s[:2000]})
                continue

            tool_calls = delta.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                _apply_tool_calls_delta(tool_acc, tool_calls)
                await ws_send_json(
                    ws,
                    {"type": "tool_calls_delta", "tool_calls": [tool_acc[k].to_dict() for k in sorted(tool_acc)]},
                )

            content = delta.get("content")
            if isinstance(content, str) and content:
                full_text += content
                await ws_send_json(ws, {"type": "llm_delta", "delta": content})
                tts_buffer += content
                if len(tts_buffer) >= tts_flush_min_chars:
                    await tts_text_queue.put(tts_buffer)
                    tts_buffer = ""
                elif tts_flush_on_punct and tts_buffer and tts_buffer[-1] in PUNCTUATION:
                    await tts_text_queue.put(tts_buffer)
                    tts_buffer = ""

    if not stop.is_set():
        if tts_buffer:
            await tts_text_queue.put(tts_buffer)
        await tts_text_queue.put(None)

    return {
        "full_text": full_text,
        "tool_calls": [tool_acc[k].to_dict() for k in sorted(tool_acc)],
    }


async def _tts_bridge(
    *,
    client: aiohttp.ClientSession,
    ws: web.WebSocketResponse,
    req: ChatRequest,
    tts_text_queue: "asyncio.Queue[Optional[str]]",
    tts_seq_start: int,
    cancel_requested: asyncio.Event,
    stop: asyncio.Event,
) -> None:
    tts_url = os.getenv("WS_TTS_URL", "ws://localhost:9000/tts")
    allow_override = _bool_env("ALLOW_CLIENT_TTS_URL", False)
    if allow_override and req.ws_tts_url:
        tts_url = req.ws_tts_url

    headers = {}
    tts_api_key = os.getenv("WS_TTS_API_KEY", "").strip()
    if tts_api_key:
        headers["Authorization"] = f"Bearer {tts_api_key}"

    async with client.ws_connect(tts_url, headers=headers, heartbeat=20) as tts_ws:
        await tts_ws.send_str(
            json_dumps(
                {
                    "type": "start",
                    "session_id": req.session_id,
                    "audio_format": req.audio_format,
                    "sample_rate": req.sample_rate,
                    "channels": req.channels,
                }
            )
        )

        tts_seq = tts_seq_start

        async def sender_loop() -> None:
            nonlocal tts_seq
            try:
                while True:
                    if stop.is_set():
                        break
                    text = await tts_text_queue.get()
                    if text is None:
                        break
                    await tts_ws.send_str(
                        json_dumps({"type": "text_delta", "session_id": req.session_id, "seq": tts_seq, "text": text})
                    )
                    tts_seq += 1

                if cancel_requested.is_set():
                    await tts_ws.send_str(
                        json_dumps({"type": "cancel", "session_id": req.session_id, "seq": tts_seq})
                    )
                    tts_seq += 1
                elif not stop.is_set():
                    await tts_ws.send_str(
                        json_dumps({"type": "text_end", "session_id": req.session_id, "seq": tts_seq})
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await ws_send_json(
                    ws,
                    {"type": "orchestrator_error", "code": "tts_send_error", "message": str(e)},
                )
                stop.set()

        sender_task = asyncio.create_task(sender_loop())
        try:
            async for msg in tts_ws:
                if stop.is_set():
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    obj = json.loads(msg.data)
                except Exception:
                    continue
                await ws_send_json(ws, obj)
                if obj.get("type") in {"tts_end", "error"}:
                    break
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except Exception:
                pass


async def ws_chat(request: web.Request) -> web.WebSocketResponse:
    expected = os.getenv("ORCH_API_KEY", "").strip()
    got = request.query.get("api_key", "").strip()
    if expected:
        auth = request.headers.get("Authorization", "")
        bearer = ""
        if auth:
            parts = auth.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                bearer = parts[1].strip()
        if got != expected and bearer != expected:
            raise web.HTTPUnauthorized(text="missing/invalid api_key")

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    client: aiohttp.ClientSession = request.app["client_session"]

    try:
        first = await ws.receive()
        if first.type != WSMsgType.TEXT:
            await ws.close()
            return ws
        try:
            obj = json.loads(first.data)
            req = ChatRequest.parse(obj)
        except Exception as e:
            await ws_send_json(ws, {"type": "orchestrator_error", "code": "bad_request", "message": str(e)})
            await ws.close()
            return ws

        stop = asyncio.Event()
        cancel_requested = asyncio.Event()
        tts_text_queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()

        tts_flush_min_chars = int(os.getenv("TTS_FLUSH_MIN_CHARS", "12"))
        tts_flush_on_punct = _bool_env("TTS_FLUSH_ON_PUNCT", True)

        start_ms = time.perf_counter()
        await ws_send_json(
            ws,
            {
                "type": "orchestrator_start",
                "session_id": req.session_id,
                "tts_flush_min_chars": tts_flush_min_chars,
                "tts_flush_on_punct": tts_flush_on_punct,
            },
        )

        tts_task = asyncio.create_task(
            _tts_bridge(
                client=client,
                ws=ws,
                req=req,
                tts_text_queue=tts_text_queue,
                tts_seq_start=1,
                cancel_requested=cancel_requested,
                stop=stop,
            )
        )

        async def client_cancel_loop() -> None:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    x = json.loads(msg.data)
                except Exception:
                    continue
                if x.get("type") == "cancel":
                    cancel_requested.set()
                    stop.set()
                    break

        cancel_task = asyncio.create_task(client_cancel_loop())

        stop_task: Optional[asyncio.Task[bool]] = None
        cancelled_by_client = False

        try:
            llm_task: "asyncio.Task[Dict[str, Any]]" = asyncio.create_task(
                _stream_sglang_deltas(
                    client=client,
                    prompt=req.prompt,
                    ws=ws,
                    tts_text_queue=tts_text_queue,
                    tts_flush_min_chars=tts_flush_min_chars,
                    tts_flush_on_punct=tts_flush_on_punct,
                    stop=stop,
                )
            )

            stop_task = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait({llm_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if stop_task in done and not llm_task.done():
                llm_task.cancel()
                try:
                    await llm_task
                except Exception:
                    pass
                await ws_send_json(ws, {"type": "orchestrator_cancelled"})
                cancelled_by_client = cancel_requested.is_set()

                if cancelled_by_client:
                    try:
                        await asyncio.wait_for(tts_task, timeout=5.0)
                    except Exception:
                        pass
            else:
                llm_res: Dict[str, Any] = llm_task.result()
                await ws_send_json(
                    ws,
                    {
                        "type": "llm_done",
                        "elapsed_ms": int((time.perf_counter() - start_ms) * 1000),
                        "full_text_len": len(llm_res.get("full_text", "")),
                        "tool_calls": llm_res.get("tool_calls", []),
                    },
                )

            # Wait for TTS to end (tts_end/error), unless client cancelled.
            if not cancelled_by_client and not cancel_requested.is_set():
                try:
                    await asyncio.wait_for(tts_task, timeout=120.0)
                except Exception:
                    pass
        finally:
            try:
                tts_text_queue.put_nowait(None)
            except Exception:
                pass

            for task in [cancel_task, tts_task]:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass

            if stop_task is not None:
                try:
                    stop_task.cancel()
                    await stop_task
                except Exception:
                    pass

            await ws.close()

        return ws
    except asyncio.CancelledError:
        raise
    except Exception as e:
        try:
            await ws_send_json(ws, {"type": "orchestrator_error", "code": "internal_error", "message": str(e)})
        except Exception:
            pass
        await ws.close()
        return ws


async def healthz(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def on_startup(app: web.Application) -> None:
    app["client_session"] = aiohttp.ClientSession()


async def on_cleanup(app: web.Application) -> None:
    await app["client_session"].close()


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/chat", ws_chat)
    return app


def main() -> None:
    host = os.getenv("ORCH_HOST", "0.0.0.0")
    port = int(os.getenv("ORCH_PORT", "9100"))
    app = create_app()
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
