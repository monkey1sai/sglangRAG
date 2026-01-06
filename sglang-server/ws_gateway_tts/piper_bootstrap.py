from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_PIPER_RELEASE_TAG = "2023.11.14-2"
DEFAULT_PIPER_LINUX_X86_64_URL = (
    "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
)
DEFAULT_PIPER_LINUX_X86_64_SHA256 = "A50CB45F355B7AF1F6D758C1B360717877BA0A398CC8CBE6D2A7A3A26E225992"

DEFAULT_MODEL_NAME = "zh_CN-huayan-medium"
DEFAULT_MODEL_ONNX_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
)
DEFAULT_MODEL_ONNX_SHA256 = "9929917BF8CABB26FD528EA44D3A6699C11E87317A14765312420BE230BE0F3D"
DEFAULT_MODEL_JSON_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"
)
DEFAULT_MODEL_JSON_SHA256 = "D521DC45504A8CCC99E325822B35946DD701840BFB07E3DBB31A40929ED6A82B"


@dataclass(frozen=True)
class PiperDownloadConfig:
    root_dir: Path
    release_tag: str
    tar_url: str
    tar_sha256: str
    model_name: str
    model_onnx_url: str
    model_onnx_sha256: str
    model_json_url: str
    model_json_sha256: str


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _download(url: str, dest: Path, *, timeout_s: int = 1200) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ws_gateway_tts/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp, dest.open("wb") as out:
        while True:
            buf = resp.read(1024 * 1024)
            if not buf:
                break
            out.write(buf)


def _download_with_sha256(url: str, dest: Path, sha256_expected: str) -> None:
    tmp = dest.with_suffix(dest.suffix + ".partial")
    if tmp.exists():
        tmp.unlink()
    _download(url, tmp)
    got = _sha256_file(tmp)
    exp = sha256_expected.strip().upper()
    if got != exp:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 不符合: {dest.name} expected={exp} got={got}")
    tmp.replace(dest)


def _acquire_lock(lock_dir: Path, *, timeout_s: float = 1800.0) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            lock_dir.mkdir(parents=True, exist_ok=False)
            return
        except FileExistsError:
            if time.time() > deadline:
                raise RuntimeError(f"等待 Piper 下載鎖逾時: {lock_dir}")
            time.sleep(1.0)


def _release_lock(lock_dir: Path) -> None:
    try:
        shutil.rmtree(lock_dir)
    except Exception:
        pass


def _write_wrapper(wrapper_path: Path, target_path: Path) -> None:
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(f"#!/bin/sh\nexec \"{target_path}\" \"$@\"\n", encoding="utf-8")
    st = wrapper_path.stat()
    wrapper_path.chmod(st.st_mode | 0o111)


def _install_piper_tar(cfg: PiperDownloadConfig) -> None:
    piper_root = cfg.root_dir
    installs_dir = piper_root / "installs"
    install_dir = installs_dir / cfg.release_tag
    current_dir = piper_root / "current"
    wrapper_path = piper_root / "piper"

    if current_dir.exists() and (current_dir / "piper").exists() and wrapper_path.exists():
        return

    installs_dir.mkdir(parents=True, exist_ok=True)
    install_dir.mkdir(parents=True, exist_ok=True)

    def safe_extractall(tf: tarfile.TarFile, dest: Path) -> None:
        dest_abs = dest.resolve()
        for member in tf.getmembers():
            member_path = (dest / member.name).resolve()
            if not str(member_path).startswith(str(dest_abs) + os.sep):
                raise RuntimeError(f"tar 檔路徑不安全: {member.name}")
        tf.extractall(path=dest)

    print(f"[ws_gateway_tts] piper bootstrap: install release={cfg.release_tag} into {install_dir}", flush=True)

    with tempfile.TemporaryDirectory(prefix="piper_extract_") as td:
        td_path = Path(td)
        tar_path = td_path / "piper.tar.gz"
        print(f"[ws_gateway_tts] downloading piper tarball: {cfg.tar_url}", flush=True)
        _download_with_sha256(cfg.tar_url, tar_path, cfg.tar_sha256)

        with tarfile.open(tar_path, "r:gz") as tf:
            safe_extractall(tf, td_path)

        candidates = [p for p in td_path.rglob("piper") if p.is_file()]
        if not candidates:
            raise RuntimeError("Piper tar.gz 內找不到 piper 執行檔")

        candidate = candidates[0]
        extracted_root = candidate.parent

        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.copytree(extracted_root, install_dir)

    if current_dir.exists() or current_dir.is_symlink():
        try:
            shutil.rmtree(current_dir)
        except Exception:
            try:
                current_dir.unlink()
            except Exception:
                pass
    try:
        current_dir.symlink_to(install_dir, target_is_directory=True)
    except Exception:
        shutil.copytree(install_dir, current_dir)

    target_bin = current_dir / "piper"
    if not target_bin.exists():
        raise RuntimeError("Piper 安裝完成但 current/piper 不存在")
    st = target_bin.stat()
    target_bin.chmod(st.st_mode | 0o111)
    _write_wrapper(wrapper_path, target_bin)


def _default_model_paths(piper_root: Path, model_name: str) -> tuple[Path, Path]:
    models_dir = piper_root / "models"
    return models_dir / f"{model_name}.onnx", models_dir / f"{model_name}.onnx.json"


def _install_default_model(cfg: PiperDownloadConfig) -> None:
    onnx_path, json_path = _default_model_paths(cfg.root_dir, cfg.model_name)
    if onnx_path.exists() and json_path.exists():
        return
    print(f"[ws_gateway_tts] downloading piper model: {cfg.model_onnx_url}", flush=True)
    _download_with_sha256(cfg.model_onnx_url, onnx_path, cfg.model_onnx_sha256)
    print(f"[ws_gateway_tts] downloading piper model json: {cfg.model_json_url}", flush=True)
    _download_with_sha256(cfg.model_json_url, json_path, cfg.model_json_sha256)


def _load_cfg() -> PiperDownloadConfig:
    root_dir = Path(_env("PIPER_ROOT", "/opt/piper"))
    return PiperDownloadConfig(
        root_dir=root_dir,
        release_tag=_env("PIPER_RELEASE_TAG", DEFAULT_PIPER_RELEASE_TAG),
        tar_url=_env("PIPER_TARBALL_URL", DEFAULT_PIPER_LINUX_X86_64_URL),
        tar_sha256=_env("PIPER_TARBALL_SHA256", DEFAULT_PIPER_LINUX_X86_64_SHA256),
        model_name=_env("PIPER_DEFAULT_MODEL_NAME", DEFAULT_MODEL_NAME),
        model_onnx_url=_env("PIPER_MODEL_ONNX_URL", DEFAULT_MODEL_ONNX_URL),
        model_onnx_sha256=_env("PIPER_MODEL_ONNX_SHA256", DEFAULT_MODEL_ONNX_SHA256),
        model_json_url=_env("PIPER_MODEL_JSON_URL", DEFAULT_MODEL_JSON_URL),
        model_json_sha256=_env("PIPER_MODEL_JSON_SHA256", DEFAULT_MODEL_JSON_SHA256),
    )


def ensure_piper_ready() -> None:
    cfg = _load_cfg()
    lock_dir = cfg.root_dir / ".bootstrap_lock"
    _acquire_lock(lock_dir)
    try:
        _install_piper_tar(cfg)
        _install_default_model(cfg)

        piper_bin = Path(_env("PIPER_BIN", str(cfg.root_dir / "piper")))
        default_model_path = _default_model_paths(cfg.root_dir, cfg.model_name)[0]
        piper_model = Path(_env("PIPER_MODEL", str(default_model_path)))

        if piper_model != default_model_path and not piper_model.exists():
            onnx_url = _env("PIPER_MODEL_ONNX_URL", cfg.model_onnx_url)
            onnx_sha = _env("PIPER_MODEL_ONNX_SHA256", cfg.model_onnx_sha256)
            json_url = _env("PIPER_MODEL_JSON_URL", cfg.model_json_url)
            json_sha = _env("PIPER_MODEL_JSON_SHA256", cfg.model_json_sha256)
            _download_with_sha256(onnx_url, piper_model, onnx_sha)
            _download_with_sha256(json_url, Path(str(piper_model) + ".json"), json_sha)

        if not piper_bin.exists():
            raise RuntimeError(f"PIPER_BIN 不存在: {piper_bin}")
        if not piper_model.exists():
            raise RuntimeError(f"PIPER_MODEL 不存在: {piper_model}")
    finally:
        _release_lock(lock_dir)


def get_piper_health_fields() -> dict:
    cfg = _load_cfg()
    piper_bin = Path(os.getenv("PIPER_BIN", str(cfg.root_dir / "piper")))
    piper_model = Path(os.getenv("PIPER_MODEL", str(_default_model_paths(cfg.root_dir, cfg.model_name)[0])))

    model_json = Path(str(piper_model) + ".json")
    model_sr: Optional[int] = None
    if model_json.exists():
        try:
            obj = json.loads(model_json.read_text(encoding="utf-8"))
            sr = obj.get("audio", {}).get("sample_rate")
            if isinstance(sr, int):
                model_sr = sr
        except Exception:
            model_sr = None

    return {
        "piper_root": str(cfg.root_dir),
        "piper_binary_exists": piper_bin.exists(),
        "piper_model_exists": piper_model.exists(),
        "model_sample_rate": model_sr,
        "default_model_name": cfg.model_name,
    }
