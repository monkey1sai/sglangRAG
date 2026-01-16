"""
Termination condition checker for SAGA outer loop.

Implements composite termination conditions:
1. Maximum iterations reached
2. Score convergence
3. All goals achieved
4. Pareto front stability
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TerminationConfig:
    """Configuration for termination conditions."""
    max_iters: int = 10
    convergence_eps: float = 0.001
    convergence_patience: int = 3
    goal_thresholds: dict = None  # goal_name -> threshold
    pareto_patience: int = 3
    
    def __post_init__(self):
        if self.goal_thresholds is None:
            self.goal_thresholds = {}


class TerminationChecker:
    """Checks composite termination conditions for outer loop.
    
    The loop terminates when ANY of the following conditions is met:
    1. Maximum iterations reached
    2. Score converged (change < eps for patience iterations)
    3. All goals achieved (above thresholds)
    4. Pareto front stable (unchanged for patience iterations)
    """
    
    def __init__(self, config: TerminationConfig):
        """Initialize with termination configuration.
        
        Args:
            config: TerminationConfig with all threshold values
        """
        self.max_iters = config.max_iters
        self.convergence_eps = config.convergence_eps
        self.convergence_patience = config.convergence_patience
        self.goal_thresholds = config.goal_thresholds
        self.pareto_patience = config.pareto_patience
        
        self._termination_reason: Optional[str] = None
        
        logger.info(
            f"[TerminationChecker] Initialized: max_iters={self.max_iters}, "
            f"eps={self.convergence_eps}, patience={self.convergence_patience}"
        )
    
    def should_stop(self, state) -> bool:
        """Check if outer loop should terminate.
        
        Args:
            state: LoopState with iteration info and score history
            
        Returns:
            True if any termination condition is met
        """
        # Condition 1: Maximum iterations reached
        if state.iteration >= self.max_iters:
            self._termination_reason = f"Reached max iterations ({state.iteration}/{self.max_iters})"
            logger.info(f"[TerminationChecker] STOP: {self._termination_reason}")
            return True
        
        # Condition 2: Score converged
        if self._is_converged(state.score_history):
            self._termination_reason = f"Score converged (eps={self.convergence_eps})"
            logger.info(f"[TerminationChecker] STOP: {self._termination_reason}")
            return True
        
        # Condition 3: All goals achieved
        if self._all_goals_achieved(state):
            self._termination_reason = "All goals achieved"
            logger.info(f"[TerminationChecker] STOP: {self._termination_reason}")
            return True
        
        # Condition 4: Pareto front stable
        if self._pareto_stable(state.pareto_history):
            self._termination_reason = "Pareto front stable"
            logger.info(f"[TerminationChecker] STOP: {self._termination_reason}")
            return True
        
        logger.debug(
            f"[TerminationChecker] Continue: iteration={state.iteration}, "
            f"best_score={state.best_score:.4f}"
        )
        return False
    
    def get_termination_reason(self, state) -> str:
        """Get the reason for termination.
        
        Should be called after should_stop() returns True.
        """
        if self._termination_reason:
            return self._termination_reason
        
        # Re-check to determine reason
        self.should_stop(state)
        return self._termination_reason or "Unknown"
    
    def _is_converged(self, score_history: List[float]) -> bool:
        """Check if scores have converged."""
        if len(score_history) < self.convergence_patience + 1:
            return False
        
        recent = score_history[-self.convergence_patience:]
        first_score = score_history[-(self.convergence_patience + 1)]
        
        # Check if all recent changes are below epsilon
        for score in recent:
            if abs(score - first_score) > self.convergence_eps:
                return False
        
        return True
    
    def _all_goals_achieved(self, state) -> bool:
        """Check if all goals are above their thresholds."""
        if not self.goal_thresholds:
            return False
        
        if not state.analysis_reports:
            return False
        
        latest_report = state.analysis_reports[-1]
        goal_achievement = latest_report.goal_achievement
        
        # Handle both dict and list formats for thresholds
        if isinstance(self.goal_thresholds, dict):
            for goal, threshold in self.goal_thresholds.items():
                if goal_achievement.get(goal, 0) < threshold:
                    return False
        elif isinstance(self.goal_thresholds, list):
            for i, threshold in enumerate(self.goal_thresholds):
                goal = f"goal_{i}"
                if goal_achievement.get(goal, 0) < threshold:
                    return False
        
        return True
    
    def _pareto_stable(self, pareto_history: List[int]) -> bool:
        """Check if Pareto front has been stable."""
        if len(pareto_history) < self.pareto_patience + 1:
            return False
        
        recent = pareto_history[-self.pareto_patience:]
        first_count = pareto_history[-(self.pareto_patience + 1)]
        
        # Check if Pareto count unchanged
        return all(count == first_count for count in recent)
    
    def get_status(self) -> dict:
        """Get current termination checker status for UI display."""
        return {
            "max_iters": self.max_iters,
            "convergence_eps": self.convergence_eps,
            "convergence_patience": self.convergence_patience,
            "goal_thresholds": self.goal_thresholds,
            "pareto_patience": self.pareto_patience,
            "last_reason": self._termination_reason
        }
