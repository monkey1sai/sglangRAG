from __future__ import annotations

import os
import sys

from .piper_bootstrap import ensure_piper_ready


def main() -> None:
    engine = os.getenv("WS_TTS_ENGINE", "piper").strip().lower()
    if engine == "piper":
        ensure_piper_ready()

    from .server import main as server_main

    server_main()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ws_gateway_tts] fatal: {e}", file=sys.stderr)
        raise

