"""
SAGA Server - WebSocket endpoint for streaming OuterLoop events.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dataclasses import asdict

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from saga.config import SagaConfig
from saga.runner import SagaRunner
from saga.outer_loop import IterationResult, FinalReport, HumanReviewRequest, LogEvent, HumanReviewType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan context manager."""
    # Startup
    cfg = SagaConfig()
    runner = SagaRunner(cfg)
    app.state.runner = runner
    
    # Ensure run directory exists before mounting
    run_dir_path = Path(cfg.run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)
    app.mount("/runs", StaticFiles(directory=run_dir_path), name="runs")
    
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """Health check endpoint."""
    return {"ok": True}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    runner: SagaRunner = ws.app.state.runner
    await ws.accept()
    
    try:
        data = await ws.receive_json()
        text = data.get("text", "")
        keywords = data.get("keywords", [])
        mode = data.get("mode", "semi-pilot")
        run_id = data.get("run_id") or None
        config_overrides = data.get("config", {})
        
        await ws.send_json({"type": "run_started", "run_id": run_id or "pending"})
        
        # Execute SAGA Runner (Async Iterator)
        async for event in runner.run(
            text=text, 
            keywords=keywords, 
            mode=mode, 
            run_id=run_id,
            config_overrides=config_overrides
        ):
            if isinstance(event, IterationResult):
                # Send iteration update
                await ws.send_json({
                    "type": "iteration_update",
                    "iteration": event.iteration
                })
                
                # Send analysis report (convert dataclass to dict)
                report_dict = asdict(event.analysis_report)
                await ws.send_json({
                    "type": "analysis_report",
                    "report": report_dict
                })
                
                # Also verify if run ID is available now
                if not run_id: 
                    # Runner generates ID if not provided, but we don't easily get it back 
                    # unless we yield it or set it on the runner. 
                    # For now, runner.run handles it internally.
                    pass

            elif isinstance(event, HumanReviewRequest):
                # Send review request
                # HumanReviewRequest uses 'data' dict to store context
                report_data = None
                if event.review_type == "analyze" or event.review_type == HumanReviewType.ANALYZE:
                    report_data = event.data.get("report")
                
                await ws.send_json({
                    "type": "need_review",
                    "message": event.message,
                    "report": asdict(report_data) if report_data else None
                })
                
                # Wait for user approval
                logger.info(f"Waiting for human review for iteration {event.iteration}")
                while True:
                    try:
                        msg = await ws.receive_json()
                        msg_type = msg.get("type")
                        if msg_type == "approve":
                            logger.info("Received approval from user.")
                            break
                        elif msg_type == "cancel":
                            logger.info("Received cancellation from user.")
                            return
                        else:
                            logger.warning(f"Received unexpected message while waiting for review: {msg}")
                    except Exception as e:
                        logger.error(f"Error waiting for review response: {e}")
                        pass

            elif isinstance(event, LogEvent):
                await ws.send_json({
                    "type": "system_log",
                    "level": event.level,
                    "message": event.message,
                    "timestamp": event.timestamp
                })

            elif isinstance(event, FinalReport):
                await ws.send_json({
                    "type": "run_finished",
                    "run_id": event.run_id,
                    "best_candidate": event.best_candidate,
                    "termination_reason": event.termination_reason
                })

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws.send_json({"type": "ui_error", "message": str(e)})
    finally:
        try:
            await ws.close()
        except:
            pass
