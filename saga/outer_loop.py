"""
Multi-round outer loop controller for SAGA objective evolution.

This module implements the outer loop that orchestrates:
- Analyzer → Planner → Implementer → Optimizer cycle
- Dynamic constraint addition based on analysis feedback
- Termination condition checking
- Human review checkpoints based on operation mode
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from enum import Enum

from saga.config import SagaConfig
from saga.search.generators import AnalysisReport, CandidateGenerator, Selector

logger = logging.getLogger(__name__)


@dataclass
class LoopState:
    """State maintained across outer loop iterations."""
    iteration: int = 0
    text: str = ""
    keywords: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)
    current_scores: List[List[float]] = field(default_factory=list)
    best_candidate: str = ""
    best_score: float = 0.0
    score_history: List[float] = field(default_factory=list)
    pareto_history: List[int] = field(default_factory=list)
    weights: List[float] = field(default_factory=lambda: [0.33, 0.34, 0.33])
    goal_thresholds: Dict[str, float] = field(default_factory=dict)
    analysis_reports: List[AnalysisReport] = field(default_factory=list)

    def update(self, new_candidates: List[tuple[str, List[float]]]) -> None:
        """Update state with new candidates from optimization."""
        if new_candidates:
            self.candidates = [c for c, _ in new_candidates]
            self.current_scores = [s for _, s in new_candidates]
            self.best_candidate = new_candidates[0][0]
            # Calculate weighted score for best candidate
            scores = new_candidates[0][1]
            if len(self.weights) == len(scores):
                self.best_score = sum(w * s for w, s in zip(self.weights, scores))
            else:
                self.best_score = sum(scores) / len(scores) if scores else 0
            self.score_history.append(self.best_score)


class HumanReviewType(Enum):
    """Types of human review requests."""
    ANALYZE = "analyze"
    PLAN = "plan"
    IMPLEMENT = "implement"
    APPROVE_CONSTRAINTS = "approve_constraints"


@dataclass
class HumanReviewRequest:
    """Request for human review during loop execution."""
    review_type: HumanReviewType
    data: Dict[str, Any]
    message: str
    iteration: int


@dataclass
class IterationResult:
    """Result of a single outer loop iteration."""
    iteration: int
    analysis_report: AnalysisReport
    new_constraints: List[str]
    best_candidate: str
    best_score: float
    elapsed_ms: int
    needs_review: bool = False
    review_request: Optional[HumanReviewRequest] = None


@dataclass
class LogEvent:
    """System log event for UI display."""
    level: str  # "info", "warning", "error", "success"
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class FinalReport:
    """Final report after outer loop completion."""
    run_id: str
    total_iterations: int
    termination_reason: str
    best_candidate: str
    best_score: float
    score_evolution: List[float]
    all_reports: List[AnalysisReport]
    elapsed_ms: int


class OuterLoop:
    """Multi-round objective evolution controller.
    
    Orchestrates the SAGA outer loop:
    1. Analyzer: Analyze current state, identify issues
    2. Planner: Plan objective weights, suggest constraints
    3. Implementer: Generate scoring code
    4. Optimizer: Run inner loop optimization
    5. Check termination conditions
    """
    
    def __init__(
        self,
        config: SagaConfig,
        analyzer: Any,
        planner: Any,
        implementer: Any,
        optimizer: Any,
        terminator: Any,
        mode_controller: Any,
    ):
        self.config = config
        self.analyzer = analyzer
        self.planner = planner
        self.implementer = implementer
        self.optimizer = optimizer
        self.terminator = terminator
        self.mode = mode_controller
        
        logger.info(f"[OuterLoop] Initialized with mode={mode_controller.mode.value}")
    
    async def run(
        self, 
        initial_state: LoopState,
        run_id: str
    ) -> AsyncIterator[IterationResult | HumanReviewRequest | FinalReport | LogEvent]:
        """Execute the outer loop asynchronously.
        
        Yields iteration results, review requests, and final report.
        This allows the caller to handle human reviews and stream progress.
        """
        state = initial_state
        start_time = time.perf_counter()
        
        logger.info(f"[OuterLoop] Starting run {run_id}")
        yield LogEvent("info", f"Run {run_id} started. Mode: {self.mode.mode.value}")
        
        while not self.terminator.should_stop(state):
            iteration_start = time.perf_counter()
            state.iteration += 1
            
            logger.info(f"[OuterLoop] === Iteration {state.iteration} ===")
            yield LogEvent("info", f"Starting Iteration {state.iteration}...")
            
            # Step 1: Analyze
            logger.info(f"[OuterLoop] Step 1: Analyzing...")
            yield LogEvent("info", "Step 1: Analyzing current state metrics...")
            try:
                analysis_result = await self._run_async(self.analyzer.run, state)
                report = self._build_analysis_report(analysis_result, state.iteration)
                state.analysis_reports.append(report)
                yield LogEvent("success", f"Analysis complete. Found {report.pareto_count} pareto candidates.")
            except Exception as e:
                logger.error(f"[OuterLoop] Analyzer failed: {e}")
                report = self._fallback_report(state.iteration, str(e))
                yield LogEvent("error", f"Analyzer failed: {e}")
            
            # Check if human review needed for analysis
            if self.mode.requires_human_review("analyze"):
                review_request = HumanReviewRequest(
                    review_type=HumanReviewType.ANALYZE,
                    data={"report": report},
                    message=f"請審核第 {state.iteration} 輪分析報告",
                    iteration=state.iteration
                )
                logger.info(f"[OuterLoop] Requesting human review for analysis")
                yield LogEvent("warning", "Waiting for human review of analysis report...")
                yield review_request
                yield LogEvent("success", "Analysis approved.")
            
            # Step 2: Plan
            logger.info(f"[OuterLoop] Step 2: Planning...")
            yield LogEvent("info", "Step 2: Planning optimization strategy...")
            try:
                plan_result = await self._run_async(self.planner.run, {
                    "analysis": analysis_result,
                    "constraints": state.constraints,
                    "iteration": state.iteration
                })
                new_constraints = plan_result.get("new_constraints", [])
                state.constraints.extend(new_constraints)
                state.weights = plan_result.get("weights", state.weights)
                logger.info(f"[OuterLoop] New constraints: {new_constraints}")
                if new_constraints:
                    yield LogEvent("info", f"Added {len(new_constraints)} new constraints.")
            except Exception as e:
                logger.error(f"[OuterLoop] Planner failed: {e}")
                new_constraints = []
                yield LogEvent("error", f"Planner failed: {e}")
            
            # Check if human review needed for plan (Co-pilot mode)
            if self.mode.requires_human_review("plan"):
                review_request = HumanReviewRequest(
                    review_type=HumanReviewType.PLAN,
                    data={"plan": plan_result, "new_constraints": new_constraints},
                    message=f"請審核第 {state.iteration} 輪規劃結果",
                    iteration=state.iteration
                )
                logger.info(f"[OuterLoop] Requesting human review for plan")
                yield LogEvent("warning", "Waiting for human review of plan...")
                yield review_request
                yield LogEvent("success", "Plan approved.")
            
            # Step 3: Implement
            logger.info(f"[OuterLoop] Step 3: Implementing...")
            yield LogEvent("info", "Step 3: Generating scoring code (Implementer)...")
            try:
                impl_result = await self._run_async(self.implementer.run, {
                    "plan": plan_result,
                    "constraints": state.constraints
                })
                scoring_code = impl_result.get("scoring_code", "")
            except Exception as e:
                logger.error(f"[OuterLoop] Implementer failed: {e}")
                scoring_code = "def score(text, ctx): return [1.0, 1.0, 1.0]"
                yield LogEvent("error", f"Implementer failed: {e}")
            
            # Step 4: Optimize (inner loop)
            logger.info(f"[OuterLoop] Step 4: Optimizing (inner loop)...")
            yield LogEvent("info", "Step 4: Running genetic optimization (Inner Loop)...")
            try:
                optimized = await self._run_async(
                    self.optimizer.optimize,
                    state.candidates,
                    scoring_code,
                    state.weights
                )
                state.update(optimized)
                yield LogEvent("success", f"Optimization complete. Best score: {state.best_score:.4f}")
            except Exception as e:
                logger.error(f"[OuterLoop] Optimizer failed: {e}")
                yield LogEvent("error", f"Optimizer failed: {e}")
            
            iteration_elapsed = int((time.perf_counter() - iteration_start) * 1000)
            
            # Yield iteration result
            result = IterationResult(
                iteration=state.iteration,
                analysis_report=report,
                new_constraints=new_constraints,
                best_candidate=state.best_candidate,
                best_score=state.best_score,
                elapsed_ms=iteration_elapsed
            )
            
            logger.info(f"[OuterLoop] Iteration {state.iteration} complete: best_score={state.best_score:.4f}, elapsed={iteration_elapsed}ms")
            yield LogEvent("success", f"Iteration {state.iteration} finished in {iteration_elapsed}ms.")
            yield result
        
        # Generate final report
        total_elapsed = int((time.perf_counter() - start_time) * 1000)
        termination_reason = self.terminator.get_termination_reason(state)
        
        final = FinalReport(
            run_id=run_id,
            total_iterations=state.iteration,
            termination_reason=termination_reason,
            best_candidate=state.best_candidate,
            best_score=state.best_score,
            score_evolution=state.score_history,
            all_reports=state.analysis_reports,
            elapsed_ms=total_elapsed
        )
        
        logger.info(f"[OuterLoop] Run complete: {termination_reason}, total_elapsed={total_elapsed}ms")
        yield final
    
    async def _run_async(self, func, *args) -> Any:
        """Run a synchronous function in an async context."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)
    
    def _build_analysis_report(self, result: Dict[str, Any], iteration: int) -> AnalysisReport:
        """Build AnalysisReport from analyzer output."""
        return AnalysisReport(
            score_distribution=result.get("score_distribution", {}),
            goal_achievement=result.get("goal_achievement", {}),
            pareto_count=result.get("pareto_count", 0),
            improvement_trend=result.get("improvement_trend", 0.0),
            bottleneck=result.get("bottleneck", "unknown"),
            suggested_constraints=result.get("suggested_constraints", []),
            iteration=iteration,
            raw_data=result
        )
    
    def _fallback_report(self, iteration: int, error: str) -> AnalysisReport:
        """Create fallback report when analyzer fails."""
        return AnalysisReport(
            score_distribution={},
            goal_achievement={},
            pareto_count=0,
            improvement_trend=0.0,
            bottleneck=f"error: {error}",
            suggested_constraints=[],
            iteration=iteration
        )
