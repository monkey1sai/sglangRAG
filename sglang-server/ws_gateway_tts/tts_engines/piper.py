from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Tuple

from .base import AudioSpec


def _is_riff_wav(b: bytes) -> bool:
    return len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE"


def _parse_wav_pcm16(wav: bytes) -> Tuple[int, int, bytes]:
    # Minimal WAV parser for PCM16LE.
    if not _is_riff_wav(wav):
        raise ValueError("not a RIFF/WAVE")
    if len(wav) < 44:
        raise ValueError("wav too small")

    view = memoryview(wav)
    offset = 12
    fmt: Optional[Tuple[int, int, int]] = None  # (channels, sample_rate, bits_per_sample)
    data: Optional[bytes] = None

    def u16(le: bytes) -> int:
        return int.from_bytes(le, "little", signed=False)

    def u32(le: bytes) -> int:
        return int.from_bytes(le, "little", signed=False)

    while offset + 8 <= len(wav):
        chunk_id = bytes(view[offset : offset + 4])
        size = u32(bytes(view[offset + 4 : offset + 8]))
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(wav):
            break

        if chunk_id == b"fmt ":
            if size < 16:
                raise ValueError("wav fmt chunk too small")
            audio_format = u16(bytes(view[payload_start + 0 : payload_start + 2]))
            channels = u16(bytes(view[payload_start + 2 : payload_start + 4]))
            sample_rate = u32(bytes(view[payload_start + 4 : payload_start + 8]))
            bits_per_sample = u16(bytes(view[payload_start + 14 : payload_start + 16]))
            if audio_format != 1:
                raise ValueError(f"wav unsupported audio_format={audio_format}")
            fmt = (channels, sample_rate, bits_per_sample)

        elif chunk_id == b"data":
            data = bytes(view[payload_start:payload_end])

        offset = payload_end + (size % 2)  # word-aligned chunks
        if fmt and data is not None:
            break

    if not fmt or data is None:
        raise ValueError("wav missing fmt/data")
    channels, sample_rate, bits = fmt
    if bits != 16:
        raise ValueError(f"wav unsupported bits_per_sample={bits}")
    return sample_rate, channels, data


@dataclass(frozen=True)
class PiperConfig:
    bin_path: str
    model_path: str
    speaker_id: Optional[int] = None
    extra_args: Tuple[str, ...] = ()


class PiperTtsEngine:
    """
    Piper TTS adapter（開源、可本地部署）。

    需求：
    - 安裝 piper CLI（可用環境變數 PIPER_BIN 指定）
    - 下載對應語音模型（.onnx；用 PIPER_MODEL 指定）

    說明：
    - Piper 模型通常有固定 sample_rate / channels；本引擎會要求與 AudioSpec 相同，否則報錯。
    - 目前實作以「每次輸入文字 → 產生一段 PCM16」為主；串流語音的粒度由 Gateway flush 規則與 Orchestrator buffering 決定。
    """

    def __init__(self, cfg: PiperConfig):
        self.cfg = cfg

    @staticmethod
    def from_env() -> "PiperTtsEngine":
        bin_path = os.getenv("PIPER_BIN", "").strip()
        model_path = os.getenv("PIPER_MODEL", "").strip()
        if not bin_path:
            raise RuntimeError("缺少環境變數 PIPER_BIN（piper 可執行檔路徑）")
        if not model_path:
            raise RuntimeError("缺少環境變數 PIPER_MODEL（piper .onnx 模型路徑）")

        speaker_id_env = os.getenv("PIPER_SPEAKER_ID", "").strip()
        speaker_id = int(speaker_id_env) if speaker_id_env else None

        extra = os.getenv("PIPER_EXTRA_ARGS", "").strip()
        extra_args = tuple(x for x in extra.split() if x) if extra else ()

        return PiperTtsEngine(PiperConfig(bin_path=bin_path, model_path=model_path, speaker_id=speaker_id, extra_args=extra_args))

    async def synthesize_pcm16(self, text: str, *, spec: AudioSpec) -> bytes:
        if not text:
            return b""

        out_mode = os.getenv("PIPER_OUTPUT_MODE", "file").strip().lower()
        if out_mode not in {"file", "stdout"}:
            out_mode = "file"

        if out_mode == "stdout":
            wav = await self._run_stdout(text)
        else:
            wav = await self._run_tempfile(text)

        if _is_riff_wav(wav):
            sr, ch, pcm = _parse_wav_pcm16(wav)
            if sr != spec.sample_rate:
                raise RuntimeError(f"piper sample_rate={sr} 與 spec.sample_rate={spec.sample_rate} 不一致")
            if ch != spec.channels:
                raise RuntimeError(f"piper channels={ch} 與 spec.channels={spec.channels} 不一致")
            return pcm

        # 若 CLI 直接輸出 raw PCM16（少數版本/參數），則直接回傳。
        return wav

    async def synthesize_pcm16_stream(self, text: str, *, spec: AudioSpec, chunk_bytes: int = 8192) -> AsyncIterator[bytes]:
        pcm = await self.synthesize_pcm16(text, spec=spec)
        for i in range(0, len(pcm), chunk_bytes):
            yield pcm[i : i + chunk_bytes]

    def _build_args(self, *, output_file: str) -> Tuple[str, ...]:
        args = [self.cfg.bin_path, "--model", self.cfg.model_path, "--output_file", output_file]
        if self.cfg.speaker_id is not None:
            args += ["--speaker", str(self.cfg.speaker_id)]
        if self.cfg.extra_args:
            args += list(self.cfg.extra_args)
        return tuple(args)

    async def _run_tempfile(self, text: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name

        args = self._build_args(output_file=out_path)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None
        proc.stdin.write((text + "\n").encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            msg = (stderr or stdout or b"").decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"piper 執行失敗 (rc={proc.returncode}): {msg}")

        try:
            with open(out_path, "rb") as rf:
                return rf.read()
        finally:
            try:
                os.unlink(out_path)
            except Exception:
                pass

    async def _run_stdout(self, text: str) -> bytes:
        args = self._build_args(output_file="-")
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write((text + "\n").encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        out = await proc.stdout.read()
        stderr = await proc.stderr.read() if proc.stderr else b""
        rc = await proc.wait()
        if rc != 0:
            msg = (stderr or out or b"").decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"piper 執行失敗 (rc={rc}): {msg}")
        return out

