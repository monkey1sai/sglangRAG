# GEMINI.md - Context for AI Assistants

This file provides a comprehensive overview of the **SAGA + Real-time Voice AI Project** to assist AI agents in understanding the codebase, architecture, and development workflows.

## 1. Project Overview

This repository houses two main, interconnected systems:
1.  **SAGA Framework**: An experimental AI agent framework designed to strictly decouple "Goal Evolution" (Outer Loop) from "Candidate Search" (Inner Loop). It aims to optimize text generation tasks through structured analysis and planning.
2.  **Real-time Voice AI Infrastructure**: A production-grade, low-latency streaming architecture combining SGLang (LLM), WebSocket Gateway (TTS), and an Orchestrator to provide instant voice interaction capabilities.

**Key Technologies:**
- **Languages**: Python (Backend/AI), JavaScript/React (Frontend), PowerShell (Scripts).
- **Core AI**: SGLang (LLM Inference), Piper/Riva (TTS).
- **Infrastructure**: Docker, Docker Compose, Nginx.
- **Protocols**: WebSocket (for real-time streaming), HTTP.

## 2. Directory Structure

- **`saga/`**: Core SAGA framework source code.
    - `modules/`: Analyzer, Planner, Implementer, Optimizer.
    - `search/`: Beam search implementation (Inner Loop).
    - `scoring/`: Sandbox for executing scoring plugins.
    - `runner.py`: Main entry point for running SAGA cycles.
- **`orchestrator/`**: Python-based middleware managing the WebSocket conversation flow.
    - `server.py`: Handles `Web Client <-> LLM <-> TTS` streaming logic.
- **`sglang-server/`**: Configuration and scripts for the inference and TTS services.
    - `ws_gateway_tts/`: The WebSocket TTS Gateway service.
    - `benchmark_*.py`: Stress testing scripts.
- **`web_client/`**: React-based frontend for the chat interface and SAGA workflow visualization.
- **`docker/`**: Dockerfiles for various services.
- **`docs/`**: Detailed project documentation (API, Deploy, Specs).
- **`scripts/`**: Helper scripts (e.g., `up.ps1` for Windows setup).

## 3. Architecture & Constraints

### SAGA Framework
- **Outer Loop**: Single-turn (MVP) for verifying architecture. Modules: Analyzer -> Planner -> Implementer -> Optimizer.
- **Inner Loop**: Pluggable search strategies (default: Beam Search).
- **Optimizer**: Execution-only; does *not* modify goals or scoring functions.
- **Replay**: Guarantees behavioral replay (logic paths), not bit-level LLM determinism.

### Voice Infrastructure
- **Flow**: `Client (Mic/Text)` -> `Orchestrator` -> `SGLang (LLM)` -(Stream)-> `Orchestrator` -(Stream)-> `WS Gateway (TTS)` -> `Client (Audio)`.
- **Performance**: Optimized for RTX 4060 Ti 8GB. Uses `RadixAttention` and `Continuous Batching` in SGLang.

## 4. Development & Operation

### Setup
1.  **Environment**: Copy `.env.example` to `.env` and configure `SGLang` API keys.
2.  **Install**: Use `uv` or `venv` for Python environments.
    - `scripts/setup_local_dirs.ps1` (initial folder creation).

### Running Services
- **Full Stack (Docker)**:
    ```powershell
    powershell -ExecutionPolicy Bypass -File scripts/up.ps1
    ```
    - SGLang: `http://localhost:8082`
    - Orchestrator: `ws://localhost:9100/chat`
    - TTS Gateway: `ws://localhost:9000/tts`
    - Web UI: `http://localhost:8080`

- **SAGA Demo (Local)**:
    ```powershell
    python -m examples.demo_run --use-sglang
    ```

### Common Tasks
- **Linting/Formatting**: Follow existing conventions (PEP 8 for Python).
- **Testing**:
    - SAGA logic: `pytest tests/`
    - Performance: `python sglang-server/benchmark_final.py`
- **Frontend Dev**:
    ```powershell
    cd web_client
    npm install && npm run dev
    ```

## 5. Key Configuration Files
- **`docker-compose.yml`**: Service definitions and networking.
- **`.env`**: Critical secrets and configuration (API keys, model paths).
- **`requirements.txt`**: Python dependencies.
- **`saga/config.py`**: Configuration class for the SAGA runner.

## 6. Important Notes for Agents
- **Do NOT commit `.env` or `models/`**.
- **Use `cmd /c`** when running shell commands on Windows to ensure stability.
- **Check `README.md`** for the latest "Implementation Status" and TODOs.
- When modifying SAGA, adhere strictly to the **Outer/Inner loop decoupling** principle.
