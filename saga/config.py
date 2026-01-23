"""Configuration for SAGA runs."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool_from_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


@dataclass
class SagaConfig:
    """Runtime config for SAGA components."""
    run_dir: str = field(default_factory=lambda: os.getenv("SAGA_RUN_DIR", "runs"))
    beam_width: int = field(default_factory=lambda: int(os.getenv("SAGA_BEAM_WIDTH", "3")))
    max_iters: int = field(default_factory=lambda: int(os.getenv("SAGA_MAX_ITERS", "2")))
    
    sglang_url: str = field(default_factory=lambda: os.getenv(
        "SAGA_SGLANG_URL", 
        f"{os.getenv('SGLANG_BASE_URL', 'http://localhost:8082').rstrip('/')}/v1/chat/completions"
    ))
    
    timeout_s: float = field(default_factory=lambda: float(os.getenv("SAGA_TIMEOUT_S", "10.0")))
    sglang_api_key: str = field(default_factory=lambda: os.getenv("SGLANG_API_KEY", ""))
    
    use_sglang: bool = field(default_factory=lambda: _bool_from_env(
        "SAGA_USE_SGLANG", 
        not _bool_from_env("SAGA_MOCK", False)
    ))
    
    use_llm_modules: bool = field(default_factory=lambda: _bool_from_env(
        "SAGA_USE_LLM_MODULES", 
        not _bool_from_env("SAGA_MOCK", False)
    ))
    
    use_groq: bool = field(default_factory=lambda: _bool_from_env("SAGA_USE_GROQ", False))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))

    def run_path(self, run_id: str) -> Path:
        """Return run output directory for the given run_id."""
        return Path(self.run_dir) / run_id

    @classmethod
    def from_file(cls, path: str) -> "SagaConfig":
        """Load config from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)
