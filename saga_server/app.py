"""
SAGA Server - WebSocket endpoint for streaming OuterLoop events.
Enhanced with pause/stop control and agent-level logging.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from dataclasses import asdict
from enum import Enum
from typing import Optional

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from saga.config import SagaConfig
from saga.runner import SagaRunner
from saga.outer_loop import IterationResult, FinalReport, HumanReviewRequest, LogEvent, HumanReviewType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RunState(Enum):
    """State of a SAGA run."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"


class RunController:
    """Controller for managing run state (pause/stop)."""
    
    def __init__(self):
        self.state = RunState.IDLE
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_requested = False
        self._current_result: Optional[dict] = None
    
    def start(self):
        self.state = RunState.RUNNING
        self._stop_requested = False
        self._pause_event.set()
        self._current_result = None
    
    def pause(self):
        if self.state == RunState.RUNNING:
            self.state = RunState.PAUSED
            self._pause_event.clear()
            return True
        return False
    
    def resume(self):
        if self.state == RunState.PAUSED:
            self.state = RunState.RUNNING
            self._pause_event.set()
            return True
        return False
    
    def stop(self):
        self._stop_requested = True
        self.state = RunState.STOPPING
        self._pause_event.set()  # Unblock if paused
        return True
    
    def complete(self):
        self.state = RunState.COMPLETED
    
    def should_stop(self) -> bool:
        return self._stop_requested
    
    async def wait_if_paused(self):
        """Wait if the run is paused."""
        await self._pause_event.wait()
    
    def set_current_result(self, result: dict):
        self._current_result = result
    
    def get_current_result(self) -> Optional[dict]:
        return self._current_result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan context manager."""
    # Startup
    cfg = SagaConfig()
    runner = SagaRunner(cfg)
    app.state.runner = runner
    app.state.controllers = {}  # run_id -> RunController
    
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
    controllers: dict = ws.app.state.controllers
    await ws.accept()
    
    controller = RunController()
    run_id = None
    
    try:
        data = await ws.receive_json()
        text = data.get("text", "")
        keywords = data.get("keywords", [])
        mode = data.get("mode", "semi-pilot")
        run_id = data.get("run_id") or None
        config_overrides = data.get("config", {})
        
        # Register controller
        if run_id:
            controllers[run_id] = controller
        
        controller.start()
        await ws.send_json({"type": "run_started", "run_id": run_id or "pending", "state": controller.state.value})
        
        # Start listening for control messages in background
        control_task = asyncio.create_task(_handle_control_messages(ws, controller))
        
        # Execute SAGA Runner (Async Iterator)
        async for event in runner.run(
            text=text, 
            keywords=keywords, 
            mode=mode, 
            run_id=run_id,
            config_overrides=config_overrides
        ):
            # Check if stop requested
            if controller.should_stop():
                logger.info(f"Stop requested for run {run_id}")
                await ws.send_json({
                    "type": "run_stopped",
                    "run_id": run_id,
                    "current_result": controller.get_current_result()
                })
                break
            
            # Wait if paused
            if controller.state == RunState.PAUSED:
                await ws.send_json({"type": "run_paused", "run_id": run_id})
            await controller.wait_if_paused()
            
            if isinstance(event, IterationResult):
                # Save current result for potential stop
                controller.set_current_result({
                    "iteration": event.iteration,
                    "best_candidate": event.best_candidate,
                    "best_score": event.best_score
                })
                
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

            elif isinstance(event, HumanReviewRequest):
                # Send review request
                report_data = None
                if event.review_type == "analyze" or event.review_type == HumanReviewType.ANALYZE:
                    report_data = event.data.get("report")
                
                await ws.send_json({
                    "type": "need_review",
                    "message": event.message,
                    "report": asdict(report_data) if report_data else None
                })
                
                # Wait for user approval (handled by control task)
                logger.info(f"Waiting for human review for iteration {event.iteration}")
                while True:
                    if controller.should_stop():
                        break
                    try:
                        # Short timeout to allow checking stop flag
                        await asyncio.wait_for(controller.wait_if_paused(), timeout=0.5)
                        # Check if approved via control messages
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=0.5)
                        msg_type = msg.get("type")
                        if msg_type == "approve":
                            logger.info("Received approval from user.")
                            break
                        elif msg_type == "cancel" or msg_type == "stop":
                            logger.info("Received stop from user during review.")
                            controller.stop()
                            break
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Error waiting for review response: {e}")
                        break

            elif isinstance(event, LogEvent):
                await ws.send_json({
                    "type": "system_log",
                    "level": event.level,
                    "message": event.message,
                    "timestamp": event.timestamp
                })

            elif isinstance(event, FinalReport):
                controller.complete()
                await ws.send_json({
                    "type": "run_finished",
                    "run_id": event.run_id,
                    "best_candidate": event.best_candidate,
                    "best_score": event.best_score,
                    "termination_reason": event.termination_reason,
                    "total_iterations": event.total_iterations,
                    "elapsed_ms": event.elapsed_ms
                })
        
        control_task.cancel()

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws.send_json({"type": "ui_error", "message": str(e)})
    finally:
        if run_id and run_id in controllers:
            del controllers[run_id]
        try:
            await ws.close()
        except:
            pass


async def _handle_control_messages(ws: WebSocket, controller: RunController):
    """Background task to handle control messages (pause/resume/stop)."""
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
                msg_type = msg.get("type")
                
                if msg_type == "pause":
                    if controller.pause():
                        logger.info("Run paused")
                        await ws.send_json({"type": "pause_ack", "state": "paused"})
                
                elif msg_type == "resume":
                    if controller.resume():
                        logger.info("Run resumed")
                        await ws.send_json({"type": "resume_ack", "state": "running"})
                
                elif msg_type == "stop":
                    controller.stop()
                    logger.info("Stop requested")
                    await ws.send_json({"type": "stop_ack", "state": "stopping"})
                    break
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Control message error: {e}")
                break
    except asyncio.CancelledError:
        pass
